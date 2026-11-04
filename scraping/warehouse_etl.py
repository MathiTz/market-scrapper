"""CLI for the warehouse ETL.

    python -m warehouse_etl --status
    python -m warehouse_etl --limit 50
    python -m warehouse_etl --rebuild-taxonomy
    python -m warehouse_etl --ncm-only
    python -m warehouse_etl --ncm-gtin-csv data/ncm/gtin.csv
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
    parser.add_argument("--force-outside", action="store_true",
                        help="reclassify the products the previous taxonomy left outside it")
    parser.add_argument("--ncm-only", action="store_true",
                        help="fill ncm_code on the products already classified, without reclassifying")
    parser.add_argument("--ncm-unmapped", action="store_true",
                        help="code the products the maps cannot reach (no leaf, no barcode)")
    parser.add_argument("--classify-unmapped", action="store_true",
                        help="classify the products with no leaf (snapshot-only or parked outside)")
    parser.add_argument("--ncm-gtin-csv", type=str,
                        help="import gtin,ncm answers (a paid provider export) before anything else")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if args.ncm_gtin_csv:
        etl.import_gtin_csv(args.ncm_gtin_csv)
    if args.status:
        return etl.status()
    if args.ncm_unmapped:
        return etl.fill_unmapped_ncm(workers=args.workers, limit=args.limit)
    if args.classify_unmapped:
        return etl.classify_unmapped(workers=args.workers, limit=args.limit)
    if args.ncm_only:
        return etl.apply_ncm()
    return etl.run(limit=args.limit, product_id=args.product, force=args.force,
                   rebuild_taxonomy=args.rebuild_taxonomy, workers=args.workers,
                   force_outside=args.force_outside)


if __name__ == "__main__":
    sys.exit(main())
