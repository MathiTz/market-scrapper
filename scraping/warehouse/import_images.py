"""Import operator-reviewed images (the Cosmos lookups in data/missing-images) into the warehouse.

The CSV carries three statuses, and they map to three different outcomes:

* ``OK``     - brand and product confirmed -> ``warehouse_images.status = 'ok'`` (served)
* ``REVIEW`` - plausible but a different GTIN/size/flavour -> ``status = 'review'`` (stored, not
               served, and never retried by the snapshot ETL until a human decides)
* ``NONE``   - nothing found -> no row, stays flagged

Images are re-encoded through the same 400 px WebP path as the rest of the mirror, so a bad file
(a 41x138 GIF, an HTML error page) is rejected here instead of reaching the table.

    python -m warehouse_import_images --csv data/missing-images/final_lookup.csv
    python -m warehouse_import_images --csv ... --dry-run
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from config import BASE_DIR
from services import image_mirror
from services.image_enrichment import name_similarity
from warehouse import db
from warehouse.etl import now

logger = logging.getLogger(__name__)

STATUS_MAP = {"OK": "ok", "REVIEW": "review"}


def _flagged_products(connection) -> List[dict]:
    return [dict(row) for row in connection.execute(
        """select w.product_key, s.raw_name, s.gtin
           from warehouse_images w left join silver_products s
             on s.canonical_product_key = w.product_key
           where w.status = 'flagged' order by s.raw_name""")]


def _match(row: dict, candidates: List[dict]) -> Optional[dict]:
    """The flagged product this CSV row refers to.

    The CSV numbers follow the order of the flagged list, so the number is tried first - but only
    when the names actually resemble each other, so a reordered list cannot silently attach an
    image to the wrong product.
    """
    try:
        index = int(row["num"]) - 1
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(candidates):
        candidate = candidates[index]
        if name_similarity(row["name"], candidate.get("raw_name")) >= 0.40:
            return candidate
    gtin = (row.get("gtin_input") or "").strip()
    if gtin:
        for candidate in candidates:
            if (candidate.get("gtin") or "").endswith(gtin.zfill(14)) or \
                    (candidate.get("gtin") or "") == gtin:
                return candidate
    best = max(candidates, key=lambda c: name_similarity(row["name"], c.get("raw_name")), default=None)
    if best and name_similarity(row["name"], best.get("raw_name")) >= 0.75:
        return best
    return None


def import_csv(path: str, images_dir: Optional[str] = None, dry_run: bool = False) -> Dict[str, int]:
    csv_path = Path(path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    image_root = Path(images_dir) if images_dir else csv_path.parent / "images"
    db.init()
    connection = db.connect()
    report = {"ok": 0, "review": 0, "skipped_status": 0, "skipped_file": 0, "skipped_match": 0}
    try:
        candidates = _flagged_products(connection)
        for row in rows:
            status = STATUS_MAP.get((row.get("status") or "").strip().upper())
            if status is None:
                report["skipped_status"] += 1
                continue
            filename = (row.get("file") or "").strip()
            if not filename:
                report["skipped_file"] += 1
                continue
            source = image_root / filename
            if not source.is_file():
                report["skipped_file"] += 1
                continue
            candidate = _match(row, candidates)
            if candidate is None:
                report["skipped_match"] += 1
                logger.warning("no flagged product matched CSV row %s (%s)", row.get("num"), row.get("name"))
                continue
            prepared = image_mirror.prepare(source.read_bytes(), min_side=40)
            if prepared is None:
                report["skipped_file"] += 1
                logger.warning("%s is not a usable image; skipped", filename)
                continue
            webp, width, height = prepared
            digest = hashlib.sha256(webp).hexdigest()
            relative = Path("images") / digest[:2] / f"{digest}.webp"
            absolute = Path(BASE_DIR) / relative
            decision = {
                "source": "cosmos",
                "csv_status": row["status"],
                "note": row.get("note") or "",
                "matched_name": row.get("matched_name") or "",
                "matched_gtin": row.get("matched_gtin") or "",
                "original_file": filename,
            }
            if not dry_run:
                absolute.parent.mkdir(parents=True, exist_ok=True)
                if not absolute.exists():
                    absolute.write_bytes(webp)
                connection.execute(
                    """insert into warehouse_images
                         (product_key, sha256, path, width, height, bytes, source_kind, source_url,
                          status, decision, checked_at)
                       values (?, ?, ?, ?, ?, ?, 'cosmos', ?, ?, ?, ?)
                       on conflict(product_key) do update set
                         sha256=excluded.sha256, path=excluded.path, width=excluded.width,
                         height=excluded.height, bytes=excluded.bytes, source_kind=excluded.source_kind,
                         source_url=excluded.source_url, status=excluded.status,
                         decision=excluded.decision, checked_at=excluded.checked_at""",
                    (candidate["product_key"], digest, str(relative), width, height, len(webp),
                     row.get("image_url") or "", status,
                     json.dumps(decision, ensure_ascii=False), now()))
            report[status] += 1
        if not dry_run:
            connection.commit()
    finally:
        connection.close()
    return report
