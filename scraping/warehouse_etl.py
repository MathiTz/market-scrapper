"""CLI for the warehouse ETL.

    python -m warehouse_etl --status
    python -m warehouse_etl --limit 50
    python -m warehouse_etl --rebuild-taxonomy
"""

import argparse
import logging
import sys

from warehouse import etl


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--status", action="store_true", help="report coverage and exit")
    parser.add_argument("--limit", type=int, help="classify at most N products")
    parser.add_argument("--product", type=int, help="classify a single product id")
    parser.add_argument("--workers", type=int, default=4, help="concurrent cloud batches (default 4)")
    parser.add_argument("--force", action="store_true", help="reclassify products already done")
    parser.add_argument("--rebuild-taxonomy", action="store_true",
                        help="re-seed dim_category from the CSV")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if args.status:
        return etl.status()
    return etl.run(limit=args.limit, product_id=args.product, force=args.force,
                   rebuild_taxonomy=args.rebuild_taxonomy, workers=args.workers)


if __name__ == "__main__":
    sys.exit(main())
