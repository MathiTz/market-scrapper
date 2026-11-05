"""Keep what every chain lists right now in the cloud database (``current_prices``, see ``db/schema.sql``).

The published snapshot is capped per chain (``config.SNAPSHOT_OFFERS_PER_CHAIN``), because the browser downloads
all of it. The full-catalogue search (``GET /api/search``) reads this table instead: one row per product and chain,
the price the chain currently lists - taken from the same "latest run of each chain" the snapshot is built from
(``public_api.latest_listed_prices``), so the two never disagree about what is for sale.

The table is replaced as a whole, in one transaction (readers see the old rows until it commits), after each
publish. It is never emptied by a run that found nothing listed.

    python -m services.listings --dry-run    # count what would be written
    python -m services.listings              # replace the table in PUBLISH_DATABASE_URL
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import psycopg
from sqlalchemy.orm import Session

import config
from models import Product, Store
from models.database import SessionLocal, init_db
from services.price_points import product_key
from services.public_api import display_name, latest_listed_prices

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
# product_key, store, display_name, price_cents, regular_price_cents, deal_label, source_url, observed_at, stock
Row = Tuple[str, str, str, int, Optional[int], Optional[str], Optional[str], datetime, Optional[int]]
COLUMNS = "product_key, store, display_name, price_cents, regular_price_cents, deal_label, source_url, observed_at, stock"


def _utc(moment: Optional[datetime]) -> datetime:
    moment = moment or datetime.now(timezone.utc)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def collect(db: Session) -> List[Row]:
    """One row per (product key, chain): the price currently listed. Products that share a key (names that
    differ only in case) keep the most recently stored price."""
    canonical: Dict[str, Store] = {}
    for store in db.query(Store).order_by(Store.id).all():
        canonical.setdefault(store.name, store)
    retailer_of = {s.id: canonical[s.name] for s in db.query(Store).all()}
    names = {p.id: p.name for p in db.query(Product).all()}
    rows: Dict[Tuple[str, str], Tuple[int, Row]] = {}
    retailer_name = {r.id: r.name for r in canonical.values()}
    for (product_id, retailer_id), price in latest_listed_prices(db, retailer_of).items():
        name = names.get(product_id)
        if name is None or not price.price or price.price <= 0:
            continue
        key, chain = product_key(name), retailer_name[retailer_id]
        if (key, chain) in rows and rows[(key, chain)][0] > price.id:
            continue
        rows[(key, chain)] = (price.id, (
            key, chain, display_name(name), round(price.price * 100),
            round(price.regular_price * 100) if price.regular_price and price.regular_price > price.price else None,
            price.offer or None, price.url or None, _utc(price.scraped_at), price.stock,
        ))
    return [row for _, row in rows.values()]


def sync(dsn: str, db: Session, connect: Callable = psycopg.connect, dry_run: bool = False) -> int:
    """Replace ``current_prices`` with what is listed now; returns the rows written (or that would be)."""
    rows = collect(db)
    if not rows:
        logger.warning("Nothing is listed locally; leaving current_prices as it is")
        return 0
    if dry_run:
        return len(rows)
    with connect(dsn) as conn:  # one transaction: committed when the block ends without an error
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM current_prices")
            with cursor.copy(f"COPY current_prices ({COLUMNS}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="count the rows without writing them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not config.PUBLISH_DATABASE_URL:
        print("Set PUBLISH_DATABASE_URL (the cloud Postgres connection string) in .env first.", file=sys.stderr)
        return 2
    init_db()
    db = SessionLocal()
    try:
        written = sync(config.PUBLISH_DATABASE_URL, db, dry_run=args.dry_run)
    finally:
        db.close()
    print(f"{'Would write' if args.dry_run else 'Wrote'} {written} current price(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
