"""The warehouse's category for each product, and the department the site can show as a chip.

Same idea as ``ncm_index``: the publisher reads ``warehouse.db`` once (cached by file stamp) and
copies the result into the snapshot, so the website never opens the database and the warehouse stays
a local file.

Two rules matter here:

* A product the Cosmos tree has no node for (``fora-da-taxonomia``) has no Cosmos leaf, but it may
  still get a *department* from its NCM heading (``data/ncm/heading-department.csv``): fresh fruit
  under Hortifruti, nappies under "Fraldas e Absorventes", and so on. That keeps the Cosmos tree
  untouched while the product still lands in a believable chip. A product whose code is not in that
  table (or has no code at all) gets nothing and stays under "Todas" and search.
* "Department" is the level the chip row shows: the eight departments of the food branch (Bebidas,
  Matinais, ...), and the branch itself for the smaller three (Higiene e Beleza, Limpeza), which have
  no comparable middle level.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple

from services.identity import canonical_key
from warehouse import config as warehouse_config
from warehouse.ncm import department_for, read_heading_departments

FOOD_ROOT = "Alimentos e Bebidas"
OUTSIDE = warehouse_config.OUTSIDE_SLUG

_CACHE: Dict[str, object] = {"stamp": None, "index": {}}

# (Cosmos leaf slug or None, department)
Entry = Tuple[Optional[str], str]


def department_of(path: str) -> str:
    """The chip a Cosmos path belongs to - see the module docstring."""
    parts = [part.strip() for part in (path or "").split(">") if part.strip()]
    if not parts:
        return ""
    if parts[0] == FOOD_ROOT and len(parts) > 1:
        return parts[1]
    return parts[0]


def category_by_key(path: Optional[Path] = None) -> Dict[str, Entry]:
    """``{canonical_product_key: (category_slug, department)}`` for every classified product."""
    target = Path(path or warehouse_config.WAREHOUSE_DB)
    try:
        stat = target.stat()
    except OSError:
        return {}
    stamp = (str(target), stat.st_mtime_ns, stat.st_size)
    if _CACHE["stamp"] == stamp:
        return _CACHE["index"]  # type: ignore[return-value]

    index: Dict[str, Entry] = {}
    headings = read_heading_departments()
    try:
        connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            for key, slug, category_path, ncm_code in connection.execute(
                    "select canonical_product_key, category_slug, category_path, ncm_code "
                    "from silver_products where category_slug is not null"):
                if slug == OUTSIDE:
                    department = department_for(ncm_code, headings)
                    if department:
                        index[key] = (None, department)
                else:
                    index[key] = (slug, department_of(category_path))
        finally:
            connection.close()
    except sqlite3.Error:
        index = {}

    _CACHE["stamp"] = stamp
    _CACHE["index"] = index
    return index


def category_for(product: dict, index: Optional[Dict[str, Entry]] = None) -> Optional[Entry]:
    """``(slug, department)`` for one product (``{"name": ..., "gtin": ...}``), or None."""
    return (index if index is not None else category_by_key()).get(canonical_key(product))
