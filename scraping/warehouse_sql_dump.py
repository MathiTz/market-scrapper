"""Write ``warehouse.db`` as one self-contained SQL file (a baseline to load, test and restore from).

The warehouse is 25 MB of SQLite, most of it the classification cache: a plain SQL dump is the
portable form, and gzipping it keeps the file small enough to commit and hand around.

    python warehouse_sql_dump.py                       # data/warehouse-baseline.sql.gz
    python warehouse_sql_dump.py --plain                # no compression
    python warehouse_sql_dump.py --out /tmp/wh.sql.gz

Load it into an empty file (the dump creates its own tables):

    rm -f warehouse.db && gunzip -c data/warehouse-baseline.sql.gz | sqlite3 warehouse.db
"""

from __future__ import annotations

import argparse
import gzip
import sqlite3
import sys
from pathlib import Path

from warehouse import config

DEFAULT_OUT = config.BASE_DIR / "data" / "warehouse-baseline.sql.gz"


def dump(source: Path, target: Path) -> int:
    """Write the schema and every row of ``source`` to ``target``; returns the bytes written."""
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        opener = gzip.open if target.suffix == ".gz" else open
        with opener(target, "wt", encoding="utf-8", newline="\n") as handle:
            # The dump carries no transaction of its own: one statement at a time lets sqlite3 report
            # which table failed instead of aborting the whole load.
            for statement in connection.iterdump():
                if statement in ("BEGIN TRANSACTION;", "COMMIT;"):
                    continue
                handle.write(statement + "\n")
    finally:
        connection.close()
    return target.stat().st_size


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--database", type=Path, default=config.WAREHOUSE_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--plain", action="store_true", help="write plain SQL instead of .sql.gz")
    args = parser.parse_args(argv)

    out = args.out.with_name(args.out.name.removesuffix(".gz")) if args.plain else args.out  # x.sql.gz -> x.sql
    if not args.database.is_file():
        print(f"no warehouse at {args.database}", file=sys.stderr)
        return 2
    written = dump(args.database, out)
    print(f"wrote {out} ({written / 1024 / 1024:.1f} MiB) from {args.database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
