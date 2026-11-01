"""Keep the product catalogue in the cloud database (``products``, see ``db/schema.sql``).

``snapshots`` only carries the products some chain lists *right now*, and ``price_points`` is keyed by a hash of
the product's name: once a chain stops listing something, its price history in Neon would have no name, brand,
barcode or photo to go with it. This module copies every product the local database has ever stored, keyed by the
same ``product_key`` as ``price_points`` (md5 of the lower-cased name), so the history can always be read back as
a product - and so a receipt's barcode can be matched against the whole catalogue, not just today's listings.

Rows are upserted. A value a source once gave is never erased by a later run that has none (the same
backfill-only rule as ``_get_or_create_product``), ``first_seen`` only moves earlier and ``last_seen`` only later,
and only rows that differ from what Neon holds are sent, so running it twice - or after a failed run - is harmless.

    python -m services.catalogue --dry-run    # count what would be sent, write nothing
    python -m services.catalogue              # sync to PUBLISH_DATABASE_URL
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import psycopg
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from models import Price, Product
from models.database import SessionLocal, init_db
from services.price_points import product_key
from services.public_api import categorize, parse_size, subcategorize

logger = logging.getLogger(__name__)

# product_key, name, brand, category, subcategory, amount, unit, pack_count, gtin, image_url, first_seen, last_seen
Row = Tuple[str, str, Optional[str], str, str, int, str, int, Optional[str], Optional[str], datetime, datetime]
# What Neon holds that decides whether a row needs sending again.
Known = Dict[str, Tuple]


def _utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def collect(db: Session) -> List[Row]:
    """One row per product key. Products that share a key (names differing only in case) are merged, taking the
    first non-empty value of each field."""
    seen: Dict[int, Tuple[datetime, datetime]] = {}  # product id -> (first, last) price observation
    for product_id, first, last in db.query(Price.product_id, func.min(Price.scraped_at), func.max(Price.scraped_at)).group_by(Price.product_id):
        seen[product_id] = (_utc(first), _utc(last))

    merged: Dict[str, dict] = {}
    for product in db.query(Product).order_by(Product.id).all():
        key = product_key(product.name)
        first_price, last_price = seen.get(product.id, (None, None))
        created = _utc(product.created_at)
        entry = merged.setdefault(key, {"name": product.name, "first": [], "last": []})
        for field in ("brand", "gtin", "image_url", "category"):
            if not entry.get(field):
                entry[field] = getattr(product, field) or None
        entry["first"] += [m for m in (created, first_price) if m]
        entry["last"] += [m for m in (last_price, created) if m]

    now = datetime.now(timezone.utc)
    rows: List[Row] = []
    for key, entry in merged.items():
        amount, unit, pack = parse_size(entry["name"])
        rows.append((
            key, entry["name"], entry.get("brand"), entry.get("category") or categorize(entry["name"]),
            subcategorize(entry["name"]), amount, unit, pack, entry.get("gtin"), entry.get("image_url"),
            min(entry["first"], default=now), max(entry["last"], default=now),
        ))
    return rows


# Positions in a Row.
BRAND, GTIN, IMAGE, FIRST_SEEN, LAST_SEEN = 2, 8, 9, 10, 11
# last_seen moves on every scrape of a listed product: a day's drift is not worth a write.
LAST_SEEN_SLACK = timedelta(hours=24)


def _differs(position: int, local, stored) -> bool:
    """Whether a local value changes what Neon holds."""
    if position in (BRAND, GTIN, IMAGE) and local is None:
        return False  # never erase what a source once gave
    if position == FIRST_SEEN:
        return local < stored
    if position == LAST_SEEN:
        return local - stored > LAST_SEEN_SLACK
    return local != stored


def plan(rows: Iterable[Row], known: Known) -> List[Row]:
    """The rows Neon is missing or holds differently. ``known`` is ``{product_key: the stored fields after the
    key}`` (what :func:`known_rows` reads)."""
    send = []
    for row in rows:
        stored = known.get(row[0])
        if stored is None or any(_differs(i, local, held) for i, (local, held) in enumerate(zip(row[1:], stored), 1)):
            send.append(row)
    return send


def known_rows(conn) -> Known:
    rows = conn.execute(
        "SELECT product_key, name, brand, category, subcategory, amount, unit, pack_count, gtin, image_url, "
        "first_seen, last_seen FROM products"
    ).fetchall()
    return {r[0]: tuple(r[1:]) for r in rows}


UPSERT = (
    "INSERT INTO products (product_key, name, brand, category, subcategory, amount, unit, pack_count, gtin, "
    "image_url, first_seen, last_seen) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (product_key) DO UPDATE SET "
    "name = EXCLUDED.name, "
    "brand = COALESCE(EXCLUDED.brand, products.brand), "
    "category = EXCLUDED.category, subcategory = EXCLUDED.subcategory, "
    "amount = EXCLUDED.amount, unit = EXCLUDED.unit, pack_count = EXCLUDED.pack_count, "
    "gtin = COALESCE(EXCLUDED.gtin, products.gtin), "
    "image_url = COALESCE(EXCLUDED.image_url, products.image_url), "
    "first_seen = LEAST(EXCLUDED.first_seen, products.first_seen), "
    "last_seen = GREATEST(EXCLUDED.last_seen, products.last_seen)"
)


def sync(dsn: str, db: Session, connect: Callable = psycopg.connect, dry_run: bool = False) -> int:
    """Send the missing or changed products to Neon; returns how many rows were sent (or would be, in a dry run)."""
    rows = collect(db)
    with connect(dsn) as conn:
        send = plan(rows, known_rows(conn))
        if send and not dry_run:
            with conn.cursor() as cursor:
                cursor.executemany(UPSERT, send)
    return len(send)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="count the rows to send without writing them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not config.PUBLISH_DATABASE_URL:
        print("Set PUBLISH_DATABASE_URL (the cloud Postgres connection string) in .env first.", file=sys.stderr)
        return 2
    init_db()
    db = SessionLocal()
    try:
        sent = sync(config.PUBLISH_DATABASE_URL, db, dry_run=args.dry_run)
    finally:
        db.close()
    print(f"{'Would send' if args.dry_run else 'Sent'} {sent} product(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
