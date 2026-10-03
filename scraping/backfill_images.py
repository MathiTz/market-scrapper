#!/usr/bin/env python
"""Backfill missing product images.

Usage
-----
    python backfill_images.py                 # fill every product with no image
    python backfill_images.py --limit 200     # stop after 200 lookups
    python backfill_images.py --ids 12,34,56  # only these product ids
    python backfill_images.py --dry-run       # report, write nothing
    python backfill_images.py --json          # machine-readable summary

Exit codes: 0 = ran (even if some products found nothing), 1 = unexpected error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from services.image_enrichment import (
    DEFAULT_MIN_SIMILARITY,
    ProductImageEnricher,
    enrich_missing_images,
)


def _parse_ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    ids = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            ids.append(int(chunk))
    return ids


def _dry_run(limit: int | None, ids: list[int] | None) -> dict:
    """Report what would be attempted without touching the network or the DB."""
    from models import Product, SessionLocal

    db = SessionLocal()
    try:
        query = db.query(Product).filter(
            (Product.image_url.is_(None)) | (Product.image_url == "")
        )
        if ids:
            query = query.filter(Product.id.in_(ids))
        query = query.order_by(Product.id)
        if limit:
            query = query.limit(limit)
        pending = query.all()
        return {
            "dry_run": True,
            "checked": len(pending),
            "updated": 0,
            "products": [
                {"product_id": p.id, "name": p.name, "gtin": p.gtin} for p in pending
            ],
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill missing product images.")
    parser.add_argument("--limit", type=int, default=None, help="max products to process")
    parser.add_argument("--ids", type=str, default=None, help="comma-separated product ids")
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=DEFAULT_MIN_SIMILARITY,
        help="name-match threshold for search-based lookups (0-1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds to sleep between HTTP requests (be polite)",
    )
    parser.add_argument("--dry-run", action="store_true", help="list work, write nothing")
    parser.add_argument("--json", action="store_true", help="print summary as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    ids = _parse_ids(args.ids)

    try:
        summary = (
            _dry_run(args.limit, ids)
            if args.dry_run
            else enrich_missing_images(
                limit=args.limit,
                only_ids=ids,
                min_name_similarity=args.min_similarity,
                request_delay=args.delay,
            )
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean message + exit 1
        logging.error("backfill failed: %s", exc, exc_info=args.verbose)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if summary.get("dry_run"):
        print(f"{summary['checked']} product(s) missing an image:")
        for row in summary["products"]:
            gtin = row["gtin"] or "-"
            print(f"  #{row['product_id']:<6} gtin={gtin:<14} {row['name']}")
        return 0

    print(
        f"checked {summary['checked']} product(s), "
        f"filled {summary['updated']} "
        f"(gtin={summary['by_source']['gtin']}, search={summary['by_source']['search']})"
    )
    for row in summary["results"]:
        if row["updated"]:
            print(f"  + #{row['product_id']} [{row['source']}] {row['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
