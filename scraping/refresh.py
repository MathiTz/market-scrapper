"""Refresh everything with one command: scrape every chain, store the prices, validate, publish.

    venv/bin/python refresh.py                   # scrape, store, validate and publish
    venv/bin/python refresh.py --only pinheiro   # scrape only some chains; the others keep their list
    venv/bin/python refresh.py --no-publish      # everything except the publish
    venv/bin/python refresh.py --skip-scrape     # validate and publish what is already stored
    venv/bin/python refresh.py --force           # publish even when validation found a blocking problem

Each chain is scraped on its own, so one that fails does not stop the others. A scrape that fails, finds
nothing, or finds far fewer items than usual is set aside and the chain's previous list stays (see
services/public_api.py), so that is a warning. What blocks the publish is a snapshot that would be worse than
the one already live: empty, with broken rows, or with under half of its offers.

Exit status: 0 when the run completed (published, or nothing new to publish), 1 when the publish was blocked
or failed, 2 when the command could not start (bad option, no publish database configured).
"""

import argparse
import json
import logging
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy import func

import config
from models import ScrapeAttempt, SessionLocal, init_db
from scraper.sites import SCRAPER_MAP
from services.public_api import _listed_runs
from services.publish import Finding, build_snapshot, check_snapshot, publish, published_offer_count
from services.scraper_service import run_all_offers
from services.store_locations import sync_store_locations


@dataclass(frozen=True)
class ChainResult:
    key: str
    name: str
    status: str  # ok | failed | empty | set aside | no result
    items: int = 0
    seconds: float = 0.0
    detail: str = ""


def evaluate_scrape(db, key: str, name: str, since_id: int) -> ChainResult:
    """How the chain's scrape went, from the attempt it recorded after ``since_id``."""
    attempt = (db.query(ScrapeAttempt)
               .filter(ScrapeAttempt.site_key == key, ScrapeAttempt.id > since_id)
               .order_by(ScrapeAttempt.id.desc()).first())
    if attempt is None:
        return ChainResult(key, name, "no result", detail="the scrape did not record a result")
    seconds = (attempt.duration_ms or 0) / 1000
    if not attempt.success:
        return ChainResult(key, name, "failed", seconds=seconds, detail=(attempt.error or "unknown error")[:200])
    if attempt.items_found <= 0:
        return ChainResult(key, name, "empty", seconds=seconds, detail="the scrape found no items")
    if _listed_runs(db, {name: key}).get(name) != attempt.run_id:
        return ChainResult(key, name, "set aside", attempt.items_found, seconds,
                           "far fewer items than usual, so the previous list stays")
    return ChainResult(key, name, "ok", attempt.items_found, seconds)


def scrape_chain(key: str, scrape: Callable = run_all_offers) -> ChainResult:
    """Scrape one chain into the local database and say how it went."""
    name = SCRAPER_MAP[key].site_name
    db = SessionLocal()
    try:
        since_id = db.query(func.max(ScrapeAttempt.id)).filter(ScrapeAttempt.site_key == key).scalar() or 0
    finally:
        db.close()
    started = time.monotonic()
    try:
        scrape(site=key)
    except Exception as exc:  # run_all_offers records a failed scraper itself; this is anything around it
        return ChainResult(key, name, "failed", seconds=time.monotonic() - started, detail=str(exc)[:200])
    db = SessionLocal()
    try:
        return evaluate_scrape(db, key, name, since_id)
    finally:
        db.close()


def _say(message: str) -> None:
    print(message, flush=True)  # each chain takes minutes: show progress as it happens, even when piped


def run(only: Optional[List[str]] = None, skip_scrape: bool = False, publish_data: bool = True,
        force: bool = False, sync_locations: bool = False, out: Callable = _say) -> int:
    dsn = config.PUBLISH_DATABASE_URL
    if publish_data and not dsn:
        out("PUBLISH_DATABASE_URL is not set in .env, so there is nowhere to publish. "
            "Set it, or use --no-publish.")
        return 2
    keys = list(only) if only else list(SCRAPER_MAP)
    unknown = [k for k in keys if k not in SCRAPER_MAP]
    if unknown:
        out(f"Unknown chain: {', '.join(unknown)}. Choose from: {', '.join(SCRAPER_MAP)}.")
        return 2
    init_db()  # adds columns introduced since the local database was created
    started = time.monotonic()
    findings: List[Finding] = []

    results: List[ChainResult] = []
    if not skip_scrape:
        out(f"1/3 Scraping {len(keys)} chain(s)"
            + ("; a full run takes a few minutes (the Cometa flyers are the slow part)." if "cometa" in keys else "."))
        for key in keys:
            result = scrape_chain(key)
            results.append(result)
            shown = f"{result.items} offers" if result.status in ("ok", "set aside") else result.status.upper()
            out(f"    {result.name:<22} {shown:<12} {result.seconds:>5.0f}s"
                + ("" if result.status == "ok" else f"   {result.detail}"))
            if result.status != "ok":
                findings.append(Finding("warning", f"{result.name}: {result.status}, {result.detail}"))
        if results and not any(r.status == "ok" for r in results):
            findings.append(Finding("error", "no chain produced fresh data"))
    else:
        out("1/3 Scraping skipped; using the prices already stored.")

    if sync_locations:
        out("    Refreshing real store branches (--sync-locations)...")
        located = sync_store_locations(site_key=only[0] if only and len(only) == 1 else None)
        if located:
            out("    " + ", ".join(f"{key}: {count}" for key, count in located.items()))
        else:
            out("    no chain with a branch source ran (see --only)")

    out("2/3 Validating.")
    db = SessionLocal()
    try:
        snapshot = build_snapshot(db)
    finally:
        db.close()
    data = json.loads(snapshot["payload"])
    findings += check_snapshot(data, published_offer_count(dsn) if dsn else None)
    coverage = data.get("coverage", {})
    out(f"    snapshot: {len(data['offers'])} offers, {len(data['products'])} products, "
        f"{coverage.get('networks', '?')} chains, {len(snapshot['payload']) // 1024} KB")
    for finding in findings:
        out(f"    {finding.level.upper():<7} {finding.message}")
    if not findings:
        out("    no problems found")

    blocking = [f for f in findings if f.level == "error"]
    if blocking and not force:
        out(f"Blocked: nothing was published, and the live data is untouched. "
            f"Fix the problem, or publish anyway with --force. ({time.monotonic() - started:.0f}s)")
        return 1
    if not publish_data:
        out(f"3/3 Publish skipped (--no-publish). ({time.monotonic() - started:.0f}s)")
        return 0
    out("3/3 Publishing." + (" (forced past the errors above)" if blocking else ""))
    try:
        wrote = publish(dsn, snapshot)
    except Exception as exc:
        out(f"Publishing failed: {exc}")
        return 1
    out(("Published." if wrote else "Nothing new: the live snapshot is already identical.")
        + f" ({time.monotonic() - started:.0f}s)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape, store, validate and publish, in one go.")
    parser.add_argument("--only", nargs="+", metavar="CHAIN", help=f"scrape only these ({', '.join(SCRAPER_MAP)})")
    parser.add_argument("--skip-scrape", action="store_true", help="validate and publish the stored prices")
    parser.add_argument("--no-publish", action="store_true", help="do everything except publish")
    parser.add_argument("--force", action="store_true", help="publish even if validation found errors")
    parser.add_argument("--sync-locations", action="store_true",
                        help="also refresh real store branch addresses (slower; they rarely change)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show the scrapers' own progress")
    args = parser.parse_args(argv)
    if not args.verbose:
        warnings.filterwarnings("ignore", category=UserWarning, module=r"torch(\.|$)")  # the OCR model's notices
    level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")
    logging.getLogger("scrapling").setLevel(level)  # Scrapling sets up its own INFO logging
    return run(only=args.only, skip_scrape=args.skip_scrape, publish_data=not args.no_publish, force=args.force,
              sync_locations=args.sync_locations)


if __name__ == "__main__":
    sys.exit(main())
