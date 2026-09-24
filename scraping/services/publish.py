"""Publish the UI's data to the cloud database (Postgres) that the Hono API reads.

The scrapers write the local SQLite database. This module builds the ``/api/public`` payload from it
(matching, categories, club prices, flyers: all the Python logic) and stores it as one row of the
``snapshots`` table (see ``db/schema.sql``). The API only serves the latest row.

    python -m services.publish                    # publish to PUBLISH_DATABASE_URL
    python -m services.publish --dry-run out.json  # only write the payload to a file
"""

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import psycopg

import config
from models.database import SessionLocal, init_db
from services.public_api import build_public

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
KEEP_SNAPSHOTS = 5  # the newest few are kept, so a bad publish can be rolled back by hand
MIN_SHARE_OF_LIVE = 0.5  # a new snapshot with fewer offers than this share of the live one is refused


@dataclass(frozen=True)
class Finding:
    level: str  # "error" blocks the publish; "warning" is only reported
    message: str


class PublishBlocked(Exception):
    """Raised by publish_current() when the data would be worse than what is already live - see
    check_snapshot. Carries the findings that caused it."""

    def __init__(self, findings: List[Finding]):
        self.findings = findings
        super().__init__("; ".join(f.message for f in findings if f.level == "error"))


def check_snapshot(data: dict, live_offers: Optional[int]) -> List[Finding]:
    """Problems with the payload about to be published, compared with the live snapshot's offer count.

    Both publishing paths go through this - refresh.py's full scrape-and-publish flow and this module's
    own publish_current() (the standalone `python -m services.publish` used for the one-time Neon setup) -
    so neither can put an empty, broken, or much-smaller-than-usual snapshot live.
    """
    findings: List[Finding] = []
    offers = data.get("offers") or []
    if not offers:
        findings.append(Finding("error", "the snapshot has no offers"))
        return findings

    product_ids = {p["id"] for p in data.get("products", [])}
    broken = [o for o in offers
              if not isinstance(o.get("price_cents"), int) or o["price_cents"] <= 0 or o.get("product_id") not in product_ids]
    if broken:
        findings.append(Finding("error", f"{len(broken)} offers have no valid price or product (first: {broken[0].get('id')})"))

    counts: Dict[str, int] = {}
    for offer in offers:
        counts[offer.get("retailer_name")] = counts.get(offer.get("retailer_name"), 0) + 1
    for retailer in data.get("retailers", []):
        if not counts.get(retailer["name"]):
            findings.append(Finding("warning", f"{retailer['name']} has no offers in the snapshot"))

    if live_offers is None:
        findings.append(Finding("warning", "could not compare with the live snapshot (none yet, or not reachable)"))
    elif len(offers) < MIN_SHARE_OF_LIVE * live_offers:
        findings.append(Finding(
            "error", f"the snapshot has {len(offers)} offers against {live_offers} live (under {MIN_SHARE_OF_LIVE:.0%})"))
    return findings


def _compact(value: dict, **options) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), **options)


# Stamped with "now" on every build, so they say nothing about whether the data changed.
_VOLATILE = {"generated_at"}
_VOLATILE_FLYER_FIELDS = {"collected_at", "source_checked_at"}


def _fingerprint(data: dict) -> str:
    stable = {k: v for k, v in data.items() if k not in _VOLATILE}
    stable["flyers"] = [{k: v for k, v in f.items() if k not in _VOLATILE_FLYER_FIELDS} for f in data.get("flyers", [])]
    return hashlib.sha256(_compact(stable, sort_keys=True).encode("utf-8")).hexdigest()


def build_snapshot(db) -> dict:
    """``{payload, etag, generated_at}`` for the current local data.

    The etag ignores the timestamps that change on every build, so publishing unchanged data twice is
    recognized as such.
    """
    data = build_public(db)
    return {"payload": _compact(data), "etag": _fingerprint(data), "generated_at": data["generated_at"]}


def publish(dsn: str, snapshot: dict, connect: Callable = psycopg.connect, keep: int = KEEP_SNAPSHOTS) -> bool:
    """Store ``snapshot`` unless the latest one has the same etag; returns whether a row was written."""
    with connect(dsn) as conn:  # commits when the block ends without an error
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        latest = conn.execute("SELECT etag FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        if latest and latest[0] == snapshot["etag"]:
            return False
        conn.execute(
            "INSERT INTO snapshots (generated_at, etag, payload) VALUES (%s, %s, %s)",
            (datetime.fromisoformat(snapshot["generated_at"]), snapshot["etag"], snapshot["payload"]),
        )
        conn.execute(
            "DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT %s)",
            (keep,),
        )
    return True


def published_offer_count(dsn: str, connect: Callable = psycopg.connect) -> Optional[int]:
    """How many offers the live snapshot holds, or None when there is none yet or it cannot be read."""
    try:
        with connect(dsn) as conn:
            row = conn.execute(
                "SELECT (payload::jsonb -> 'coverage' ->> 'offers')::int FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except Exception as exc:  # a first publish has no table yet; a network failure must not stop a refresh
        logger.info("Could not read the live snapshot's size: %s", exc)
        return None
    return row[0] if row and row[0] is not None else None


def publish_current(force: bool = False) -> Optional[bool]:
    """Build and publish the current data. ``None`` when no cloud database is configured.

    Refuses to publish (raising ``PublishBlocked``) when the local data would be worse than what is
    already live - empty, broken, or far smaller - unless ``force`` is set. This is the same check
    refresh.py's own publish step runs; this function is the *other* path that can put data live (the
    standalone `python -m services.publish` used for the one-time Neon setup), so it needs the same guard.
    """
    dsn = config.PUBLISH_DATABASE_URL
    if not dsn:
        logger.info("PUBLISH_DATABASE_URL is not set; skipping the publish step")
        return None
    init_db()  # adds columns introduced since the local database was created
    db = SessionLocal()
    try:
        snapshot = build_snapshot(db)
    finally:
        db.close()
    findings = check_snapshot(json.loads(snapshot["payload"]), published_offer_count(dsn))
    blocking = [f for f in findings if f.level == "error"]
    if blocking and not force:
        raise PublishBlocked(findings)
    wrote = publish(dsn, snapshot)
    logger.info("Snapshot %s (%d KB)", "published" if wrote else "unchanged, not published",
                len(snapshot["payload"]) // 1024)
    return wrote


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", metavar="FILE", help="write the payload to FILE instead of the database")
    parser.add_argument("--force", action="store_true", help="publish even if validation found a blocking problem")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.dry_run:
        init_db()
        db = SessionLocal()
        try:
            snapshot = build_snapshot(db)
        finally:
            db.close()
        Path(args.dry_run).write_text(snapshot["payload"], encoding="utf-8")
        print(f"Wrote {len(snapshot['payload']) // 1024} KB to {args.dry_run} (etag {snapshot['etag'][:12]})")
        return 0
    if not config.PUBLISH_DATABASE_URL:
        print("Set PUBLISH_DATABASE_URL (the cloud Postgres connection string) in .env first.", file=sys.stderr)
        return 2
    try:
        wrote = publish_current(force=args.force)
    except PublishBlocked as exc:
        print("Blocked: nothing was published, and the live data is untouched.")
        for finding in exc.findings:
            print(f"    {finding.level.upper():<7} {finding.message}")
        print("Fix the problem, or publish anyway with --force.")
        return 1
    print("Published." if wrote else "Nothing changed since the last snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
