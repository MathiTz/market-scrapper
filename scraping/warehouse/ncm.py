"""NCM — the Brazilian fiscal classification of a product — for the warehouse.

Every product should end up with one, and the warehouse resolves it in two layers, cheapest first:

* ``map_gtin_ncm`` — the answer for a *specific barcode*, from a paid provider (Cosmos Bluesoft,
  GS1) or an imported CSV. It wins because it is about that exact package, and the table means a
  barcode is ever paid for once. There is no free GTIN→NCM source: a barcode does not encode a NCM,
  which is a fiscal classification of the product, not of its packaging.
* ``map_category_ncm`` — one code per Cosmos leaf, curated in ``data/ncm/category-ncm.csv`` (drafted
  by ``warehouse_ncm_bootstrap.py``). It covers the products whose chain gave no barcode at all.

Nothing here invents a code: every value is validated against ``dim_ncm``, the official NCM table
vendored in ``data/ncm/ncm.csv`` (fetched from BrasilAPI by ``warehouse_ncm_fetch.py``). A NCM is 8
digits, the *item* level; the table also carries the 2 (chapter), 4 (heading) and 6 (subheading)
levels, so a coarser answer can be stored and every leaf can be grouped by chapter.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from warehouse import config

LEVELS = (2, 4, 6, 8)
ITEM_LEVEL = 8

# Words that say nothing about which product a description is about.
STOPWORDS = frozenset("""
a as o os um uma de do da dos das e ou em no na nos nas para por com sem que se ao aos
mais mesmo outras outros outro outra nao sim seu sua suas seus presentes
""".split())

_TAG_RE = re.compile(r"<[^>]+>")
_DIGITS_RE = re.compile(r"\D")
_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_code(raw: Optional[str]) -> Optional[str]:
    """The 2, 4, 6 or 8 digits of a NCM, or None. ``"1006.30.21"`` -> ``"10063021"``.

    BrasilAPI also returns partial display nodes (``"0101.2"``, 5 digits); those are not a level of
    the classification and are rejected rather than guessed at.
    """
    digits = _DIGITS_RE.sub("", raw or "")
    return digits if len(digits) in LEVELS else None


def clean_text(text: Optional[str]) -> str:
    """A NCM description as plain text: no HTML tags, no entities, one line. Accents are kept - they
    are part of the Portuguese description; :func:`words` folds them only to compare."""
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return " ".join(text.replace("\xa0", " ").split())


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text)
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def words(text: Optional[str]) -> frozenset:
    """The content words of a description or a category path, for scoring candidates."""
    return frozenset(w for w in _WORD_RE.findall(_fold(clean_text(text))) if len(w) >= 3 and w not in STOPWORDS)


@dataclass(frozen=True)
class Code:
    code: str
    level: int
    chapter: str
    parent: Optional[str]
    description: str


@dataclass(frozen=True)
class Answer:
    """A product's NCM and where it came from."""

    code: str
    source: str        # gtin | leaf | manual
    confidence: float


@dataclass(frozen=True)
class CategoryCode:
    slug: str
    code: str
    confidence: float
    source: str        # llm | overlap | manual
    reason: str = ""


@dataclass(frozen=True)
class Candidate:
    code: str
    description: str
    score: float


class Table:
    """The official NCM table, keyed by code."""

    def __init__(self, codes: Dict[str, Code], version: str = ""):
        self.codes = codes
        self.version = version

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Table":
        path = Path(path or config.NCM_TABLE_CSV)
        if not path.is_file():
            raise FileNotFoundError(f"NCM table not found: {path} (run warehouse_ncm_fetch.py)")
        codes: Dict[str, Code] = {}
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = normalize_code(row.get("code"))
                if code is None:
                    continue
                codes[code] = Code(
                    code=code,
                    level=len(code),
                    chapter=code[:2],
                    parent=(row.get("parent") or "").strip() or None,
                    description=(row.get("description") or "").strip(),
                )
        version = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        return cls(codes, version=version)

    # -- queries ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.codes)

    def get(self, code: str) -> Optional[Code]:
        return self.codes.get(code or "")

    def is_valid(self, code: Optional[str]) -> bool:
        return bool(code) and code in self.codes

    @property
    def items(self) -> List[Code]:
        """Every 8-digit item, the level a product's NCM is stored at."""
        return [c for c in self.codes.values() if c.level == ITEM_LEVEL]

    def require(self, code: Optional[str], where: str = "") -> Code:
        found = self.get(code or "")
        if found is None:
            raise ValueError(f"unknown NCM {code!r}{f' ({where})' if where else ''}")
        return found

    def chapter_of(self, code: str) -> Optional[str]:
        found = self.get(code)
        return found.chapter if found else None


# --------------------------------------------------------------------------- category map


def read_category_map(path: Optional[Path] = None, table: Optional[Table] = None) -> Dict[str, CategoryCode]:
    """``{category_slug: CategoryCode}`` from ``data/ncm/category-ncm.csv``.

    An unknown code fails loudly: this file is curated by hand as well as generated, and a typo
    silently applied to thousands of products is worse than a failed run.
    """
    path = Path(path or config.NCM_CATEGORY_CSV)
    if not path.is_file():
        return {}
    mapping: Dict[str, CategoryCode] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            slug = (row.get("category_slug") or "").strip()
            code = normalize_code(row.get("ncm_code"))
            if not slug:
                continue
            if code is None:
                raise ValueError(f"{path}:{line}: category {slug!r} has no valid NCM: {row.get('ncm_code')!r}")
            if table is not None and not table.is_valid(code):
                raise ValueError(f"{path}:{line}: category {slug!r} points at unknown NCM {code!r}")
            mapping[slug] = CategoryCode(
                slug=slug,
                code=code,
                confidence=_number(row.get("confidence")),
                source=(row.get("source") or "manual").strip(),
                reason=(row.get("reason") or "").strip(),
            )
    return mapping


def write_category_map(path: Path, rows: Sequence[dict]) -> int:
    """Write the category map (sorted by slug), keeping the columns the reader expects."""
    rows = sorted(rows, key=lambda r: r["category_slug"])
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "category_slug", "category_path", "category_name", "ncm_code", "ncm_description",
            "confidence", "source", "reason",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return len(rows)


def _number(value) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- candidates


def candidates(table: Table, text: str, limit: int = 40) -> List[Candidate]:
    """The NCM items whose descriptions share the most words with ``text``, best first.

    Only a shortlist: it exists so the model (or a human) chooses from a handful of plausible
    codes instead of 10,000. Scoring is deliberately simple - shared content words, with a small
    penalty for long descriptions that share words by accident ("outros", "sem", ...).
    """
    want = words(text)
    if not want:
        return []
    scored: List[Candidate] = []
    for code in table.items:
        got = words(code.description)
        shared = want & got
        if not shared:
            continue
        score = len(shared) - 0.05 * len(got - want)
        scored.append(Candidate(code.code, code.description, round(score, 3)))
    scored.sort(key=lambda c: (-c.score, len(c.description), c.code))
    return scored[:limit]


# --------------------------------------------------------------------------- resolution


def resolve(category_slug: Optional[str], gtin: Optional[str],
            category_map: Dict[str, CategoryCode],
            gtin_map: Dict[str, str]) -> Optional[Answer]:
    """The NCM for one product: its barcode's answer wins, else its leaf's."""
    if gtin and gtin in gtin_map:
        return Answer(gtin_map[gtin], "gtin", 1.0)
    mapped = category_map.get(category_slug or "")
    if mapped is not None:
        return Answer(mapped.code, "leaf", mapped.confidence)
    return None


# --------------------------------------------------------------------------- storage


def seed(connection, table: Table, mapping: Dict[str, CategoryCode]) -> int:
    """Mirror the official table and the category map into the warehouse. Returns rows written."""
    written = connection.executemany(
        """insert into dim_ncm (ncm_code, level, chapter, parent_code, description, table_version)
           values (?, ?, ?, ?, ?, ?)
           on conflict(ncm_code) do update set
             level=excluded.level, chapter=excluded.chapter, parent_code=excluded.parent_code,
             description=excluded.description, table_version=excluded.table_version""",
        [(c.code, c.level, c.chapter, c.parent, c.description, table.version) for c in table.codes.values()],
    ).rowcount
    connection.executemany(
        """insert into map_category_ncm (category_slug, ncm_code, confidence, source, reason, updated_at)
           values (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
           on conflict(category_slug) do update set
             ncm_code=excluded.ncm_code, confidence=excluded.confidence,
             source=excluded.source, reason=excluded.reason, updated_at=excluded.updated_at""",
        [(m.slug, m.code, m.confidence, m.source, m.reason) for m in mapping.values()],
    )
    return written + len(mapping)


def answers(connection) -> Dict[str, str]:
    """``{gtin: ncm_code}`` of every barcode the warehouse has an answer for."""
    return {row[0]: row[1] for row in connection.execute("select gtin, ncm_code from map_gtin_ncm")}


def import_answers(connection, rows: Iterable[tuple], source: str = "csv") -> int:
    """Store barcode answers. ``rows`` are ``(gtin, ncm_code)``; the GTIN is zero-padded to 14."""
    prepared = []
    for gtin, code in rows:
        normalized = _gtin14(gtin)
        if normalized is None or not code:
            continue
        prepared.append((normalized, str(code).strip(), source))
    if not prepared:
        return 0
    connection.executemany(
        """insert into map_gtin_ncm (gtin, ncm_code, source, confidence, fetched_at)
           values (?, ?, ?, 1.0, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
           on conflict(gtin) do update set
             ncm_code=excluded.ncm_code, source=excluded.source,
             confidence=excluded.confidence, fetched_at=excluded.fetched_at""",
        prepared,
    )
    return len(prepared)


def _gtin14(raw: Optional[str]) -> Optional[str]:
    digits = _DIGITS_RE.sub("", raw or "")
    if len(digits) not in (8, 12, 13, 14):
        return None
    return digits.zfill(14)
