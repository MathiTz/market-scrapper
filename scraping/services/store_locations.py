"""Keep ``store_locations`` (each chain's real, physical branches - see :mod:`models.store_location`) in
step with what the chain's own site reports.

Only scrapers with a ``fetch_locations()`` method participate - every chain has one at the time of writing,
each reading its own real source (see the "Real branches" note on each site in scraper/sites/); a future
chain onboarded without one is simply left with no rows, so the public API omits its location rather than
guessing one - see the note on ``Store.address`` in models/store.py.

Branch lists change rarely, so as with prices (see ``services.public_api``'s "current list" rule), a run
that finds far fewer branches than we already have is treated as partial, not as branches having closed: the
ones it did find are still saved (a real address is worth recording even from a short run), but nothing is
removed. A branch that really did close will still go once two or three ordinary runs agree it is gone.
"""

import logging
from typing import Dict, List, Optional

from models import SessionLocal, Store, StoreLocation, init_db
from scraper.base import BranchLocation
from scraper.sites import ALL_SCRAPERS, SCRAPER_MAP
from services.address_search import AddressSearchError, geocode_address

logger = logging.getLogger(__name__)

MIN_SHARE_OF_EXISTING = 0.5  # a run finding fewer than this share of the known branches is treated as partial


def sync_store_locations(site_key: Optional[str] = None) -> Dict[str, int]:
    """Fetch and store each participating chain's real branches.

    Returns ``{site_key: branches saved}`` for the chains that have a ``fetch_locations`` method; a chain
    without one, or whose fetch failed outright, is simply absent from the result.
    """
    init_db()
    if site_key:
        scraper_cls = SCRAPER_MAP.get(site_key)
        if not scraper_cls:
            raise ValueError(f"Unknown site '{site_key}'")
        scrapers = [scraper_cls]
    else:
        scrapers = ALL_SCRAPERS

    results: Dict[str, int] = {}
    for scraper_cls in scrapers:
        scraper = scraper_cls()
        fetch_locations = getattr(scraper, "fetch_locations", None)
        if fetch_locations is None:
            continue
        try:
            branches = fetch_locations()
        except Exception:
            logger.exception("[%s] Fetching branches failed", scraper.site_name)
            continue
        results[scraper.site_key] = _store_branches(scraper.site_name, branches)
    return results


def _store_branches(store_name: str, branches: List[BranchLocation]) -> int:
    db = SessionLocal()
    try:
        # The lowest id, matching the "canonical" retailer public_api.build_public resolves a chain name to
        # (stores holds duplicates from the seed script having run more than once); otherwise a branch could
        # attach to a store id the public API never looks at.
        store = db.query(Store).filter(Store.name == store_name).order_by(Store.id).first()
        if store is None:
            store = Store(name=store_name)
            db.add(store)
            db.flush()

        existing_ids = {
            eid for (eid,) in db.query(StoreLocation.external_id).filter(StoreLocation.store_id == store.id)
        }
        saved, found_ids = 0, set()
        for branch in branches:
            lat, lon = branch.lat, branch.lon
            if lat is None or lon is None:
                place = _geocode(branch.address, hint=branch.name)
                if place is None:
                    logger.warning("[%s] Could not geocode branch %r (%s)", store_name, branch.name, branch.address)
                    continue
                lat, lon = place["latitude"], place["longitude"]
            row = (
                db.query(StoreLocation)
                .filter(StoreLocation.store_id == store.id, StoreLocation.external_id == branch.external_id)
                .first()
            )
            if row is None:
                row = StoreLocation(store_id=store.id, external_id=branch.external_id)
                db.add(row)
            row.name, row.address, row.lat, row.lon = branch.name, branch.address, lat, lon
            found_ids.add(branch.external_id)
            saved += 1

        gone = existing_ids - found_ids
        if gone and saved >= MIN_SHARE_OF_EXISTING * len(existing_ids):
            db.query(StoreLocation).filter(
                StoreLocation.store_id == store.id, StoreLocation.external_id.in_(gone)
            ).delete(synchronize_session=False)
        elif gone:
            logger.warning(
                "[%s] Only %d of %d known branches were found this run; keeping the rest rather than "
                "removing them", store_name, saved, len(existing_ids),
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[%s] Failed to store branches", store_name)
        raise
    finally:
        db.close()
    return saved


def _geocode(address: str, hint: str = "") -> Optional[dict]:
    """``address`` geocoded, retrying with ``hint`` (the branch's own name) appended if that fails.

    A branch out of the home city is often named after its own city ("Sobral", "Acaraú"), which its street
    address does not always repeat ("Rua Coronel Sales, 175 - Curral Velho" alone, with no city at all) -
    Photon cannot place that on its own, so the branch name is worth trying as the missing city.
    """
    try:
        place = geocode_address(address)
        if place is None and hint and hint.casefold() not in address.casefold():
            place = geocode_address(f"{address}, {hint}, CE")
        return place
    except AddressSearchError as exc:
        logger.warning("Geocoding failed for %r: %s", address, exc)
        return None
