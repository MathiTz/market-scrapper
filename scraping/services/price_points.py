"""Keep the price history in the cloud database (``price_points``, see ``db/schema.sql``).

The local ``market.db`` only keeps the current price per product and chain, plus the last few superseded
ones (``price_history``, capped). After each publish this module copies what changed to Postgres, which has
no cap and survives a rebuilt local database:

* the first time a product/chain pair is seen there, all of its archived prices and its current one (the
  backfill);
* afterwards, the archived prices newer than what Neon already has, and the current price when it differs
  from the latest one (a price merely reconfirmed adds nothing).

Rows are keyed ``(md5 of the lower-cased product name, chain name, observed_at)`` and inserted with
``ON CONFLICT DO NOTHING``, so running it twice - or after a failed run - is harmless and catches up.
Everything stored is sent, including products a chain has stopped listing: history is kept, not hidden.

    python -m services.price_points --dry-run    # count what would be sent, write nothing
    python -m services.price_points              # sync to PUBLISH_DATABASE_URL
"""

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import psycopg
from sqlalchemy.orm import Session

import config
from models import Price, PriceHistory, Product, Store
from models.database import SessionLocal, init_db
from services.scraper_service import unpack_history

logger = logging.getLogger(__name__)

Pair = Tuple[str, str]  # (product_key, chain name)
# (observed_at, price in cents, regular price in cents or None)
Point = Tuple[datetime, int, Optional[int]]


@dataclass
class Series:
    """What the local database knows about one product at one chain."""

    archived: List[Point] = field(default_factory=list)  # superseded prices, as (last seen, cents, None)
    current: Optional[Point] = None


def product_key(name: str) -> str:
    return hashlib.md5(name.lower().encode("utf-8")).hexdigest()


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _cents(price: float) -> int:
    return round(price * 100)


def collect(db: Session, keys: Optional[Iterable[str]] = None) -> Dict[Pair, Series]:
    """The local price series per (product key, chain), for every stored price - listed lately or not.

    ``keys`` limits it to those products (the history route asks for a few at a time)."""
    wanted = set(keys) if keys is not None else None
    store_name = {s.id: s.name for s in db.query(Store).all()}
    names = {p.id: p.name for p in db.query(Product).all()}
    history = {(h.product_id, h.store_id): h.blob for h in db.query(PriceHistory).all()}

    series: Dict[Pair, Series] = {}
    for price in db.query(Price).order_by(Price.id).all():
        chain = store_name.get(price.store_id)
        name = names.get(price.product_id)
        if chain is None or name is None or not price.price or price.price <= 0:
            continue
        key = product_key(name)
        if wanted is not None and key not in wanted:
            continue
        entry = series.setdefault((key, chain), Series())
        seen = _utc(price.scraped_at or datetime.now(timezone.utc))
        regular = _cents(price.regular_price) if price.regular_price else None
        if entry.current is None or seen >= entry.current[0]:
            entry.current = (seen, _cents(price.price), regular)
        for cents, observed in unpack_history(history.get((price.product_id, price.store_id), b"")):
            if cents > 0:
                entry.archived.append((observed, cents, None))
    return series


def plan(series: Dict[Pair, Series], known: Dict[Pair, Tuple[datetime, int]]) -> List[Tuple[str, str, datetime, int, Optional[int]]]:
    """The rows Neon is missing: ``(product_key, chain, observed_at, cents, regular_cents)``.

    ``known`` is the latest ``(observed_at, price_cents)`` Neon holds for each pair.
    """
    rows = []
    for (key, chain), entry in series.items():
        latest = known.get((key, chain))
        last_seen, last_price = latest if latest else (None, None)
        for observed, cents, regular in sorted(set(entry.archived)):
            if last_seen is None or observed > last_seen:
                rows.append((key, chain, observed, cents, regular))
                last_price = cents
        if entry.current and entry.current[1] != last_price:
            observed, cents, regular = entry.current
            rows.append((key, chain, observed, cents, regular))
    return rows


def history_of(db: Session, keys: Iterable[str]) -> Dict[str, Dict[str, List[list]]]:
    """``{product_key: {chain: [[observed_at ISO, price_cents], ...]}}`` from the local database: what GET
    /api/price-history answers (the Worker answers the same from ``price_points``), oldest first."""
    history: Dict[str, Dict[str, List[list]]] = {}
    for key, chain, observed, cents, _regular in plan(collect(db, keys), {}):
        history.setdefault(key, {}).setdefault(chain, []).append([observed.isoformat(), cents])
    for chains in history.values():
        for points in chains.values():
            points.sort()
    return history


def known_points(conn) -> Dict[Pair, Tuple[datetime, int]]:
    rows = conn.execute(
        "SELECT DISTINCT ON (product_key, store) product_key, store, observed_at, price_cents "
        "FROM price_points ORDER BY product_key, store, observed_at DESC"
    ).fetchall()
    return {(key, store): (observed, cents) for key, store, observed, cents in rows}


def sync(dsn: str, db: Session, connect: Callable = psycopg.connect, dry_run: bool = False) -> int:
    """Send the missing price points to Neon; returns how many rows were new (or would be, in a dry run)."""
    series = collect(db)
    with connect(dsn) as conn:
        rows = plan(series, known_points(conn))
        if rows and not dry_run:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO price_points (product_key, store, observed_at, price_cents, regular_price_cents) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    rows,
                )
    return len(rows)


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
    print(f"{'Would send' if args.dry_run else 'Sent'} {sent} price point(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
