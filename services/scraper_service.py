"""Bridge between scrapers and the database.

Runs scrapers and saves the results (price, store, product)
into the SQLite database. Also records scrape attempts for monitoring.
"""

import logging
import struct
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import (
    Price,
    PriceHistory,
    Product,
    SessionLocal,
    Store,
    init_db,
    ScrapeAttempt,
)
from scraper.base import ProductPrice
from scraper.sites import ALL_SCRAPERS

logger = logging.getLogger(__name__)

# One row per (product, store) in `prices`, always the current price - not one row per scrape. Ad-hoc,
# irregular scraping means the old insert-every-time approach grew without bound (tens of thousands of
# rows within weeks, almost all of them superseded and never read again: nothing anywhere queries a price
# by anything but "the latest for this product and store"). A price that actually changes is archived into
# PriceHistory first, packed 8 bytes per entry instead of a JSON row each - at thousands of products times
# several observations a day, a text field name and punctuation repeated per entry adds up for something
# nobody currently reads back except in bulk (a possible future price-trend view). HISTORY_CAP makes each
# row a ring buffer, not a log that grows forever: the oldest entry drops as a new one is appended.
HISTORY_CAP = 20
_ENTRY = struct.Struct(">II")  # price in cents, observed-at as unix seconds (UTC) - 8 bytes/entry


def pack_entry(price: float, observed_at: datetime) -> bytes:
    """One past (price, observed-at) as a fixed 8-byte record."""
    cents = max(0, min(round(price * 100), 2**32 - 1))
    epoch = int(observed_at.replace(tzinfo=timezone.utc).timestamp())
    return _ENTRY.pack(cents, epoch)


def append_history(blob: bytes, entry: bytes) -> bytes:
    """`blob` with `entry` appended, oldest entries dropped past HISTORY_CAP."""
    updated = bytes(blob or b"") + entry
    cap = HISTORY_CAP * _ENTRY.size
    return updated[-cap:] if len(updated) > cap else updated


def unpack_history(blob: bytes) -> List[Tuple[int, datetime]]:
    """The packed entries as (price_cents, observed_at), oldest first - nothing reads this yet; it exists
    for a possible future price-trend view without needing a format change to add one."""
    return [(cents, datetime.fromtimestamp(epoch, tz=timezone.utc)) for cents, epoch in _ENTRY.iter_unpack(blob or b"")]


def _get_or_create_store(db: Session, store_name: str, website: Optional[str] = None) -> Store:
    """Return an existing store by name or create a new one."""
    store = db.query(Store).filter(Store.name == store_name).first()
    if store is None:
        store = Store(name=store_name, website=website or "")
        db.add(store)
        db.flush()
    return store


def _get_or_create_product(db: Session, entry: ProductPrice) -> Product:
    """Return an existing product by name (case-insensitive) or create a new one.

    Brand, GTIN and photo are filled in once and kept: only most VTEX-backed sources currently send them,
    so a later scrape of the same product from a source that does not is never allowed to erase a value an
    earlier, better-informed scrape already found.
    """
    product = db.query(Product).filter(Product.name.ilike(entry.product_name)).first()
    if product is None:
        product = Product(name=entry.product_name, brand=entry.brand, gtin=entry.gtin, image_url=entry.image_url)
        db.add(product)
        db.flush()
    else:
        if entry.brand and not product.brand:
            product.brand = entry.brand
        if entry.gtin and not product.gtin:
            product.gtin = entry.gtin
        if entry.image_url and not product.image_url:
            product.image_url = entry.image_url
    return product


def _upsert_price(db: Session, product_id: int, store_id: int, entry: ProductPrice, run_id: Optional[str]) -> None:
    """One row per (product, store) in `prices`, kept current - see this module's own note on why.

    A price that changed since the last scrape is archived into PriceHistory before being overwritten; one
    that is merely reconfirmed unchanged just refreshes this row's own `scraped_at` ("last seen at") and
    does not need a history entry of its own for that.
    """
    existing = db.query(Price).filter(Price.product_id == product_id, Price.store_id == store_id).first()
    if existing is None:
        db.add(Price(product_id=product_id, store_id=store_id, price=entry.price, url=entry.url,
                     regular_price=entry.regular_price, offer=entry.offer, stock=entry.stock, run_id=run_id))
        return
    if round(existing.price * 100) != round(entry.price * 100):
        history = db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id, PriceHistory.store_id == store_id,
        ).first()
        packed = pack_entry(existing.price, existing.scraped_at or datetime.utcnow())
        if history is None:
            db.add(PriceHistory(product_id=product_id, store_id=store_id, blob=packed))
        else:
            history.blob = append_history(history.blob, packed)
    existing.price = entry.price
    existing.url = entry.url
    existing.regular_price = entry.regular_price
    existing.offer = entry.offer
    existing.stock = entry.stock
    existing.run_id = run_id
    existing.scraped_at = datetime.utcnow()


def save_scraped_results(results: List[ProductPrice], run_id: Optional[str] = None) -> int:
    """Persist a list of scraped :class:`ProductPrice` entries, tagged with the scrape ``run_id``.

    Returns the number of prices saved (new or refreshed - see `_upsert_price`).
    """
    init_db()
    db = SessionLocal()
    saved = 0
    skipped = 0
    try:
        for entry in results:
            # A 0.0 price means the parser found no price; storing it would
            # make the item look free and win every cheapest-store comparison.
            if not entry.product_name or not entry.price or entry.price <= 0:
                skipped += 1
                continue
            store = _get_or_create_store(db, entry.store_name)
            product = _get_or_create_product(db, entry)
            _upsert_price(db, product.id, store.id, entry, run_id)
            saved += 1
        db.commit()
        logger.info("Saved %d price record(s), skipped %d without a valid price.", saved, skipped)
    except Exception:
        db.rollback()
        logger.exception("Failed to save scraped results")
        raise
    finally:
        db.close()
    return saved


def _record_attempt(site_key: str, query: Optional[str], success: bool,
                    error: Optional[str] = None, items_found: int = 0,
                    duration_ms: Optional[float] = None, run_id: Optional[str] = None) -> None:
    """Record a scrape attempt in the database for monitoring."""
    init_db()
    db = SessionLocal()
    try:
        attempt = ScrapeAttempt(
            site_key=site_key,
            query=query,
            success=success,
            error=error,
            items_found=items_found,
            duration_ms=duration_ms,
            run_id=run_id,
        )
        db.add(attempt)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to record scrape attempt for %s", site_key)
    finally:
        db.close()


def run_and_store(query: str = "", site: Optional[str] = None, limit: int = 1000) -> int:
    """Run one (or all) scrapers for ``query`` and persist results.

    Args:
        query: Search term (e.g. "arroz").
        site: Optional site key (e.g. "pao_de_acucar"); if None, run all.
        limit: Max results per site.

    Returns:
        Total number of price records saved.
    """
    if site:
        from scraper.sites import SCRAPER_MAP

        scraper_cls = SCRAPER_MAP.get(site)
        if not scraper_cls:
            raise ValueError(f"Unknown site '{site}'")
        scrapers = [scraper_cls]
    else:
        scrapers = ALL_SCRAPERS

    total = 0
    for scraper_cls in scrapers:
        scraper = scraper_cls()
        logger.info("Scraping %s for '%s'...", scraper.site_name, query)
        start_time = time.monotonic()
        run_id = uuid.uuid4().hex  # one id per site and run: the prices it saves belong to this list
        try:
            results = scraper.scrape(query, limit=limit)
            logger.info("%s returned %d results", scraper.site_name, len(results))
            saved = save_scraped_results(results, run_id=run_id)
            total += saved
            _record_attempt(
                site_key=scraper.site_key,
                query=query,
                success=True,
                items_found=len(results),
                duration_ms=(time.monotonic() - start_time) * 1000,
                run_id=run_id,
            )
        except Exception as exc:
            logger.exception("Scraper %s failed for '%s'", scraper.site_name, query)
            _record_attempt(
                site_key=scraper.site_key,
                query=query,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start_time) * 1000,
                run_id=run_id,
            )
            continue
    return total


def run_all_products(site: Optional[str] = None, limit: int = 1000) -> int:
    """Run scrapers for every product currently in the database.

    Args:
        site: Optional site key; if None, run all sites.
        limit: Max results per site per product.

    Returns:
        Total number of price records saved across all products.
    """
    init_db()
    db = SessionLocal()
    try:
        products = db.query(Product).all()
    finally:
        db.close()

    if not products:
        logger.info("No products in database to scrape.")
        return 0

    total = 0
    for product in products:
        logger.info("Scraping all sites for product '%s'...", product.name)
        total += run_and_store(product.name, site=site, limit=limit)
    return total


def run_all_offers(site: Optional[str] = None, limit: int = 1000) -> Dict[str, int]:
    """Run scrapers on their offers pages (no query) and persist results.

    Args:
        site: Optional site key; if None, run all sites.
        limit: Max results per site.

    Returns:
        Dict mapping site_key -> number of price records saved.
    """
    if site:
        from scraper.sites import SCRAPER_MAP

        scraper_cls = SCRAPER_MAP.get(site)
        if not scraper_cls:
            raise ValueError(f"Unknown site '{site}'")
        scrapers = [scraper_cls]
    else:
        scrapers = ALL_SCRAPERS

    results_by_site: Dict[str, int] = {}
    for scraper_cls in scrapers:
        scraper = scraper_cls()
        logger.info("Scraping offers from %s...", scraper.site_name)
        start_time = time.monotonic()
        run_id = uuid.uuid4().hex  # one id per site and run: the prices it saves belong to this list
        try:
            results = scraper.scrape("", limit=limit)
            logger.info("%s returned %d results", scraper.site_name, len(results))
            saved = save_scraped_results(results, run_id=run_id)
            results_by_site[scraper.site_key] = saved
            _record_attempt(
                site_key=scraper.site_key,
                query=None,
                success=True,
                items_found=len(results),
                duration_ms=(time.monotonic() - start_time) * 1000,
                run_id=run_id,
            )
        except Exception as exc:
            logger.exception("Scraper %s failed on offers page", scraper.site_name)
            results_by_site[scraper.site_key] = 0
            _record_attempt(
                site_key=scraper.site_key,
                query=None,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start_time) * 1000,
                run_id=run_id,
            )
    return results_by_site


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "arroz"
    count = run_and_store(query)
    print(f"Saved {count} price records.")