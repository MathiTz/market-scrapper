"""CLI for snapshot-driven ingestion.

    python -m warehouse_snapshot --status
    python -m warehouse_snapshot --file /tmp/snapshot.json
    python -m warehouse_snapshot --dsn "$PUBLISH_DATABASE_URL"
"""

import argparse
import logging
import os
import sys

from warehouse import snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--status", action="store_true", help="report what has been ingested")
    parser.add_argument("--file", help="read a snapshot payload from a JSON file")
    parser.add_argument("--dsn", default=os.getenv("PUBLISH_DATABASE_URL", ""),
                        help="Postgres DSN to read the newest snapshot from (default: PUBLISH_DATABASE_URL)")
    parser.add_argument("--snapshot-id", type=int, help="ingest a specific snapshot id instead of the newest")
    parser.add_argument("--limit", type=int, help="process at most N products per step")
    parser.add_argument("--no-images", action="store_true", help="skip the image step")
    parser.add_argument("--workers", type=int, default=4, help="concurrent classification batches")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if args.status:
        return snapshot.status()

    if args.file:
        payload = snapshot.read_file(args.file)
    elif args.dsn:
        payload = snapshot.read_postgres(args.dsn, args.snapshot_id)
        if payload is None:
            print("No snapshot found in the database.")
            return 1
    else:
        parser.error("give --file or --dsn (or set PUBLISH_DATABASE_URL)")

    print(f"snapshot {payload['key']} ({payload['source']}), generated {payload['generated_at']}")
    report = snapshot.ingest(payload, limit=args.limit, with_images=not args.no_images,
                             workers=args.workers)
    if report["skipped"]:
        return 0
    print(f"new products: {report['new_products']}")
    print(f"offers recorded: {report['offers']}")
    print(f"images fetched: {report['images']}")
    print(f"classified: {report['classified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
