"""The NCM of each product, read from the warehouse and keyed the way the warehouse keys it.

The website never opens ``warehouse.db``: the publisher joins this index into the snapshot it
already sends, so the warehouse stays a local file and the UI keeps its one-snapshot contract.

The index is cached by ``(path, mtime, size)``: the Flask API calls ``build_public`` per request and
re-reading a few thousand rows every time would be wasteful, while a cache that ignored the file's
stamp would hide the codes a fresh ETL run just wrote.

A missing warehouse is not an error - another machine, CI, or a first checkout simply publishes
``ncm: null`` for everything, and the UI falls back to its category-based alternatives.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Optional

from services.identity import canonical_key
from warehouse import config as warehouse_config

_CACHE: Dict[str, object] = {"stamp": None, "index": {}}


def ncm_by_key(path: Optional[Path] = None) -> Dict[str, str]:
    """``{canonical_product_key: ncm}`` for every product the warehouse has a code for."""
    target = Path(path or warehouse_config.WAREHOUSE_DB)
    try:
        stat = target.stat()
    except OSError:
        return {}
    stamp = (str(target), stat.st_mtime_ns, stat.st_size)
    if _CACHE["stamp"] == stamp:
        return _CACHE["index"]  # type: ignore[return-value]

    index: Dict[str, str] = {}
    try:
        connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            for key, code in connection.execute(
                    "select canonical_product_key, ncm_code from silver_products "
                    "where ncm_code is not null"):
                index[key] = code
        finally:
            connection.close()
    except sqlite3.Error:
        index = {}  # no warehouse / different schema: publish without NCM rather than fail

    _CACHE["stamp"] = stamp
    _CACHE["index"] = index
    return index


def ncm_for(product: dict, index: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The code for one product (``{"name": ..., "gtin": ...}``), or None when unknown."""
    return (index if index is not None else ncm_by_key()).get(canonical_key(product))
