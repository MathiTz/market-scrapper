"""Draft the leaf -> NCM map (``data/ncm/category-ncm.csv``) with the gemma4 that also classifies products.

One decision per Cosmos leaf, made from a shortlist of codes whose descriptions share words with the
leaf's path (see :func:`warehouse.ncm.candidates`) - the model never sees 10,000 codes and cannot
invent one, because the answer is checked against the official table and the shortlist.

A leaf the model cannot answer falls back to the best-scoring candidate and is marked ``overlap``
with lower confidence, so a reviewer knows which rows to read first. Manual rows already in the CSV
(the ``manual`` source) are never overwritten by a re-run.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from warehouse import config
from warehouse.classifier import _post
from warehouse.ncm import ITEM_LEVEL, Candidate, Table, candidates, normalize_code, words
from warehouse.taxonomy import Node

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Brazilian fiscal classification (NCM) expert. Give the NCM of the supermarket category "
    "the user names: 8 digits, no dots. Answer with a real code from the NCM table, never a made-up one. "
    "Categories that are not food or drink (cleaning, hygiene, household, electronics) still have a NCM - "
    "give the one that matches the product type. When candidates are listed, copy one of them exactly. "
    'Reply with JSON only: {"code":"########","confidence":0.0,"reason":"<short>"}.'
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["code", "confidence"],
}


@dataclass
class Draft:
    code: str
    confidence: float
    source: str          # llm | overlap
    reason: str = ""


def _answer_from(content: str) -> Optional[Dict]:
    """The JSON object in a model reply, tolerating code fences and prose around it."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else ""
    try:
        payload = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            payload = json.loads(text[start:end + 1])
        except ValueError:
            return None
    return payload if isinstance(payload, dict) else None


class Drafter:
    """Asks the model for a NCM, then makes the answer conform to the official table.

    Free-form first: gemma4 knows the common grocery codes (rice, beer, wine) better than word
    overlap does, and the answer is cheap to check. A code that is not in the table is a near miss
    in practice - the model answers ``10063000`` where the item is ``10063021`` - so the fallback
    narrows by subheading (6 digits) then heading (4 digits) and lets the model choose inside the
    few items that remain. Nothing that is not in the table is ever stored.
    """

    def __init__(self, table: Table, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None, min_score: float = 2.0,
                 shortlist: int = 30, workers: int = 4):
        self.table = table
        self.api_key = (api_key if api_key is not None else config.OLLAMA_API_KEY).strip()
        self.model = model or config.LLM_MODEL
        self.url = (base_url or config.OLLAMA_CLOUD_BASE_URL) + "/api/chat"
        self.min_score = min_score
        self.shortlist = shortlist
        self.workers = workers

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    # -- one item ---------------------------------------------------------

    def ask(self, node: Node) -> Optional[Draft]:
        """The best NCM this drafter can defend for one category leaf."""
        return self.for_text(f"{node.path} {node.name}")

    def for_text(self, text: str) -> Optional[Draft]:
        """The best NCM this drafter can defend for a category path *or* a product name."""
        if not self.ready:
            return self.best_overlap(text)
        draft = self._propose(text)
        if draft is None:
            return self.best_overlap(text)
        if not (self.table.is_valid(draft.code) and self.table.get(draft.code).level == ITEM_LEVEL):
            draft = self._settle(text, draft) or self.best_overlap(text)
            if draft is None:
                return None
        # A second look inside the chosen heading: the first answer often lands on the right chapter
        # and the wrong item ("Outros" for gin, rum for conhaque). Cheap, and it is what fixes those.
        return self._confirm(text, draft) or draft

    def _propose(self, text: str) -> Optional[Draft]:
        """The model's own answer, unchecked."""
        body = self._body(SYSTEM_PROMPT, f"Item: {text}")
        answer = _post(self.url, body, headers={"Authorization": f"Bearer {self.api_key}"})
        if not answer:
            return None
        payload = _answer_from((answer.get("message") or {}).get("content") or "")
        code = normalize_code((payload or {}).get("code"))
        if code is None:
            return None
        return Draft(code, _confidence(payload), "llm", str(payload.get("reason") or "")[:200])

    def _settle(self, text: str, draft: Draft) -> Optional[Draft]:
        """Narrow an off-table code to a real item: by subheading, then by heading."""
        for digits in (6, 4):
            prefix = draft.code[:digits]
            items = [c for c in self.table.items if c.code.startswith(prefix)]
            if not items:
                continue
            if len(items) == 1:
                return Draft(items[0].code, round(draft.confidence * 0.9, 3), "repaired",
                             f"only item under {prefix}")
            options = sorted(items, key=lambda c: (-_overlap(text, c.description), c.code))[:25]
            chosen = self._choose(text, options)
            if chosen:
                return Draft(chosen, round(draft.confidence * 0.85, 3), "repaired",
                             f"chosen inside {prefix}")
            return Draft(options[0].code, round(draft.confidence * 0.6, 3), "repaired",
                         f"best overlap inside {prefix}")
        return None

    def _confirm(self, text: str, draft: Draft) -> Optional[Draft]:
        heading = draft.code[:4]
        items = [c for c in self.table.items if c.code.startswith(heading)]
        if len(items) < 2:
            return None
        options = sorted(items, key=lambda c: (-_overlap(text, c.description), c.code))[:25]
        if draft.code not in [c.code for c in options]:
            options = [self.table.get(draft.code)] + options[:24]
        chosen = self._choose(text, options)
        if not chosen or chosen == draft.code:
            return None
        return Draft(chosen, round(draft.confidence * 0.95, 3), draft.source,
                     f"confirmed inside heading {heading}")

    def _choose(self, text: str, options: Sequence[Candidate]) -> Optional[str]:
        """Ask which of a handful of real items fits best."""
        listing = "\n".join(f"{c.code} | {c.description}" for c in options)
        body = self._body(SYSTEM_PROMPT, f"Item: {text}\n\nCandidatos:\n{listing}")
        answer = _post(self.url, body, headers={"Authorization": f"Bearer {self.api_key}"})
        payload = _answer_from(((answer or {}).get("message") or {}).get("content") or "")
        code = normalize_code((payload or {}).get("code"))
        return code if any(c.code == code for c in options) else None

    def _body(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0},
        }

    def best_overlap(self, text: str) -> Optional[Draft]:
        """No model: the best-scoring candidate, when the overlap is strong enough to be worth a row."""
        options = candidates(self.table, text, limit=self.shortlist)
        if not options or options[0].score < self.min_score:
            return None
        top = options[0]
        return Draft(top.code, min(0.7, 0.25 + 0.1 * top.score), "overlap", "best description overlap")


def _confidence(payload: Optional[dict]) -> float:
    try:
        return max(0.0, min(float((payload or {}).get("confidence", 0.75)), 1.0))
    except (TypeError, ValueError):
        return 0.75


def _overlap(text: str, description: str) -> int:
    return len(words(text) & words(description))


# --------------------------------------------------------------------------- the whole map


def draft_map(table: Table, leaves: Sequence[Node], drafter: Drafter,
              existing: Optional[Dict[str, dict]] = None,
              reuse: Optional[set] = None) -> List[dict]:
    """One row per leaf, keeping rows marked ``manual`` and any slug in ``reuse``.

    ``reuse`` is how ``--only-missing`` fills in new leaves without re-asking the model about the
    leaves it already answered (and without spending the calls).
    """
    existing = existing or {}
    reuse = reuse or set()
    kept = {slug: row for slug, row in existing.items()
            if (row.get("source") or "") == "manual" or slug in reuse}
    todo = [leaf for leaf in leaves if leaf.slug not in kept]

    answers: Dict[str, Optional[Draft]] = {}
    if todo:
        with ThreadPoolExecutor(max_workers=max(1, drafter.workers)) as pool:
            for node, draft in zip(todo, pool.map(drafter.ask, todo)):
                answers[node.slug] = draft

    rows: List[dict] = []
    for leaf in leaves:
        if leaf.slug in kept:
            rows.append(dict(kept[leaf.slug]))
            continue
        draft = answers.get(leaf.slug)
        if draft is None:
            continue
        found = table.get(draft.code)
        rows.append({
            "category_slug": leaf.slug,
            "category_path": leaf.path,
            "category_name": leaf.name,
            "ncm_code": draft.code,
            "ncm_description": found.description if found else "",
            "confidence": round(draft.confidence, 3),
            "source": draft.source,
            "reason": draft.reason,
        })
    return rows
