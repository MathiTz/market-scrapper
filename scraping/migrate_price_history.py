"""One-off migration: compact `prices` from one row per scrape to one row per (product, store).

Before this, every scrape inserted a new row and old ones were kept forever - ad-hoc, irregular scraping
made that grow unbounded (see services/scraper_service.py's own note on why). This keeps only the latest
row per (product_id, store_id) in `prices` and packs everything older into `price_history`, capped at
HISTORY_CAP entries per pair (see services/scraper_service.py's pack_entry/append_history).

Safe to run more than once: a (product, store) pair already down to one row is left alone. Back up
market.db first regardless - this deletes rows.

Run with:  python migrate_price_history.py
"""

import logging
from collections import defaultdict

from models import Price, PriceHistory, SessionLocal, init_db
from services.scraper_service import HISTORY_CAP, _ENTRY, append_history, pack_entry

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def migrate() -> None:
    init_db()
    db = SessionLocal()
    try:
        by_pair = defaultdict(list)
        for price in db.query(Price).order_by(Price.id).all():
            by_pair[(price.product_id, price.store_id)].append(price)

        compacted_pairs = 0
        rows_removed = 0
        archived = 0
        for (product_id, store_id), rows in by_pair.items():
            if len(rows) < 2:
                continue
            rows.sort(key=lambda r: r.id)  # oldest first, matches append order elsewhere
            history = db.query(PriceHistory).filter(
                PriceHistory.product_id == product_id, PriceHistory.store_id == store_id,
            ).first()
            blob = history.blob if history else b""
            # Old data has a row for every scrape, including many that just reconfirmed the same price -
            # archiving all of them would waste the cap on noise instead of real price changes, so only
            # the last row of each run of equal consecutive prices (the point right before it changed) is
            # kept as a history entry, exactly like the live upsert path does going forward.
            for prev, nxt in zip(rows, rows[1:]):
                if round(prev.price * 100) != round(nxt.price * 100):
                    blob = append_history(blob, pack_entry(prev.price, prev.scraped_at))
                    archived += 1
            for row in rows[:-1]:
                db.delete(row)
                rows_removed += 1
            if blob:  # every row here reconfirmed the same price - nothing to archive, no empty row to add
                if history is None:
                    db.add(PriceHistory(product_id=product_id, store_id=store_id, blob=blob))
                else:
                    history.blob = blob
            compacted_pairs += 1
        db.commit()
        kept = db.query(Price).count()
        logger.info(
            "Compacted %d (product, store) pair(s): removed %d superseded row(s) (%d archived as real price "
            "changes, %d were redundant same-price reconfirmations and simply dropped), kept %d current "
            "row(s), each history blob capped at %d entries (%d bytes).",
            compacted_pairs, rows_removed, archived, rows_removed - archived, kept,
            HISTORY_CAP, HISTORY_CAP * _ENTRY.size,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
