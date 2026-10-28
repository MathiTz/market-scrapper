"""Classify a product into the Cosmos taxonomy with gemma4.

One model, one job: pick the most specific leaf for a product name. The answer is validated against
the closed list of leaves (an invented slug is dropped, never stored) and cached by signature so a
re-run never re-pays.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import requests

from warehouse import config
from warehouse.taxonomy import Node, Taxonomy

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.S)


# --------------------------------------------------------------------------- transport


def _post(url: str, body: dict, *, headers: Optional[dict] = None, timeout: float = 180.0,
          attempts: int = 4) -> Optional[dict]:
    for attempt in range(attempts):
        try:
            response = requests.post(url, json=body, headers=headers or {}, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            logger.warning("POST %s -> HTTP %s: %s", url, response.status_code, response.text[:200])
            if response.status_code in (400, 401, 403):
                return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("POST %s failed (%s/%s): %s", url, attempt + 1, attempts, exc)
        import time
        time.sleep(1.5 * (attempt + 1))
    return None


# --------------------------------------------------------------------------- prompts


SYSTEM_PROMPT = (
    "You classify Brazilian supermarket products into a fixed category tree. "
    "Choose the single most specific category that fits the product. "
    "Products that are not food or drink (cleaning, hygiene, household, electronics) must use "
    f"the category '{config.OUTSIDE_SLUG}'. "
    "Reply with JSON only, exactly in this shape: "
    '{"items":[{"i":1,"slug":"<slug from the list>","confidence":0.0,"reason":"<short>"}]}. '
    "The 'slug' value must be copied verbatim from the list; never invent one."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "slug": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["i", "slug", "confidence"],
            },
        }
    },
    "required": ["items"],
}


def _taxonomy_block(nodes: Sequence[Node]) -> str:
    return "\n".join(f"{n.slug} | {n.path}" for n in nodes)


def _items_from(content: str) -> list:
    """Items from a model reply, tolerating code fences, a bare array, or ``{"items": ...}``."""
    text = (content or "").strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except ValueError:
        match = re.search(r"\[.*\]|\{.*\}", text, re.S)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except ValueError:
            return []
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("results") or payload.get("products") or []
    else:
        items = payload
    return items if isinstance(items, list) else []


# --------------------------------------------------------------------------- classifier


@dataclass
class Result:
    product_id: int
    slug: Optional[str]
    path: Optional[str]
    source: str
    confidence: float
    reason: str = ""


class CloudClassifier:
    """gemma4 through the Ollama Cloud API (no local daemon needed)."""

    def __init__(self, taxonomy: Taxonomy, api_key: str = None, model: str = None,
                 base_url: str = None, batch_size: int = None):
        self.taxonomy = taxonomy
        self.api_key = (api_key if api_key is not None else config.OLLAMA_API_KEY).strip()
        self.model = model or config.LLM_MODEL
        self.url = (base_url or config.OLLAMA_CLOUD_BASE_URL) + "/api/chat"
        self.batch_size = batch_size or config.LLM_BATCH_SIZE
        self._by_path = {node.path: node.slug for node in taxonomy.leaves}

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    def _nodes(self) -> List[Node]:
        outside = Node(config.OUTSIDE_SLUG, config.OUTSIDE_NAME, config.OUTSIDE_NAME, None, 1, True)
        return list(self.taxonomy.leaves) + [outside]

    def _resolve(self, value: str) -> Optional[str]:
        """A slug, or a full path when the model answered with the path instead."""
        value = (value or "").strip()
        if value in self.taxonomy.nodes or value == config.OUTSIDE_SLUG:
            return value
        return self._by_path.get(value)

    def classify_batch(self, products: Sequence[dict]) -> Dict[int, dict]:
        """``{product_id: {slug, confidence, reason}}`` for one batch."""
        if not self.ready:
            return {}
        listing = _taxonomy_block(self._nodes())
        lines = "\n".join(
            f'{index}. name="{p["name"]}" brand="{p.get("brand") or ""}"'
            for index, p in enumerate(products, start=1)
        )
        user = (
            f"Categories (slug | full path):\n{listing}\n\n"
            f"Products to classify:\n{lines}\n\n"
            f"Return one item per product, using its number as 'i'."
        )
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0},
        }
        answer = _post(self.url, body, headers={"Authorization": f"Bearer {self.api_key}"})
        if not answer:
            return {}
        items = _items_from((answer.get("message") or {}).get("content") or "")
        if not items:
            logger.warning("cloud answer had no items")
            return {}
        out: Dict[int, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("i", item.get("index", 0))) - 1
            except (TypeError, ValueError):
                continue
            slug = self._resolve(str(item.get("slug") or item.get("category") or item.get("path") or ""))
            if not (0 <= index < len(products)) or not slug:
                continue
            try:
                confidence = float(item.get("confidence", 0.75))
            except (TypeError, ValueError):
                confidence = 0.75
            out[products[index]["id"]] = {
                "slug": slug,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reason": str(item.get("reason") or "")[:300],
            }
        return out



# --------------------------------------------------------------------------- helpers


def signature(name: str, brand: Optional[str], version: str = None) -> str:
    from services.public_api import clean

    material = f"{clean(name)}::{clean(brand or '')}::{version or config.PROMPT_VERSION}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def path_of(taxonomy: Taxonomy, slug: str) -> str:
    if slug == config.OUTSIDE_SLUG:
        return config.OUTSIDE_NAME
    node = taxonomy.get(slug)
    return node.path if node else ""
