"""Import operator-reviewed images into the warehouse.

    python -m warehouse_import_images --csv data/missing-images/final_lookup.csv
    python -m warehouse_import_images --csv ... --dry-run
"""

import argparse
import logging
import sys

from warehouse import import_images


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", required=True, help="final_lookup.csv produced by the image review")
    parser.add_argument("--images", help="folder with the image files (default: ./images next to the CSV)")
    parser.add_argument("--dry-run", action="store_true", help="report what would be imported")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    report = import_images.import_csv(args.csv, args.images, dry_run=args.dry_run)
    print(("would import" if args.dry_run else "imported") +
          f": {report['ok']} ok, {report['review']} review")
    print(f"skipped: {report['skipped_status']} without a usable status, "
          f"{report['skipped_file']} unusable file, {report['skipped_match']} unmatched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
