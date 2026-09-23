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
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import psycopg

import config
from models.database import SessionLocal, init_db
from services.public_api import build_public

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
KEEP_SNAPSHOTS = 5  # the newest few are kept, so a bad publish can be rolled back by hand


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


def publish_current() -> Optional[bool]:
    """Build and publish the current data. ``None`` when no cloud database is configured."""
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
    wrote = publish(dsn, snapshot)
    logger.info("Snapshot %s (%d KB)", "published" if wrote else "unchanged, not published",
                len(snapshot["payload"]) // 1024)
    return wrote


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", metavar="FILE", help="write the payload to FILE instead of the database")
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
    print("Published." if publish_current() else "Nothing changed since the last snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
