"""Draft ``data/ncm/category-ncm.csv``: one NCM per Cosmos leaf, the map every product inherits.

    python warehouse_ncm_bootstrap.py --limit 10     # try ten leaves, print what it chose
    python warehouse_ncm_bootstrap.py                # every leaf; keeps rows marked manual
    python warehouse_ncm_bootstrap.py --only-missing # only leaves the CSV does not cover yet
    python warehouse_ncm_bootstrap.py --offline      # no model: best description overlap

Review the result before trusting it: rows with ``source=overlap`` and ``confidence`` under ~0.6 are
the ones worth reading. A wrong code on a leaf is a wrong code on every product under it.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Dict

from warehouse import config
from warehouse.ncm import Table, normalize_code, write_category_map
from warehouse.ncm_draft import Drafter, draft_map
from warehouse.taxonomy import Taxonomy


def existing_rows(path: Path) -> Dict[str, dict]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return {row["category_slug"]: row for row in csv.DictReader(handle) if row.get("category_slug")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=config.NCM_CATEGORY_CSV)
    parser.add_argument("--limit", type=int, help="only the first N leaves (a cheap trial run)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--shortlist", type=int, default=30, help="candidates shown to the model")
    parser.add_argument("--min-score", type=float, default=2.0,
                        help="overlap needed to accept a leaf without the model")
    parser.add_argument("--only-missing", action="store_true", help="keep every leaf already mapped")
    parser.add_argument("--offline", action="store_true", help="do not call the model")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    taxonomy = Taxonomy.load()
    table = Table.load()
    existing = existing_rows(args.out)
    leaves = taxonomy.leaves
    if args.limit:
        leaves = leaves[:args.limit]

    drafter = Drafter(table, api_key="" if args.offline else None,
                      min_score=args.min_score, shortlist=args.shortlist, workers=args.workers)
    if not drafter.ready and not args.offline:
        print("OLLAMA_API_KEY is not set: falling back to description overlap.", file=sys.stderr)
    reuse = set(existing) if args.only_missing else set()
    rows = draft_map(table, leaves, drafter, existing=existing, reuse=reuse)
    if not rows:
        print("no leaf produced an answer", file=sys.stderr)
        return 1

    # A partial run must not throw away the rest of the file.
    covered = {row["category_slug"] for row in rows}
    merged = [row for slug, row in existing.items() if slug not in covered] + rows

    invalid = [row["category_slug"] for row in rows
               if normalize_code(row.get("ncm_code")) is None or not table.is_valid(row["ncm_code"])]
    if invalid:
        print(f"refusing to write: {len(invalid)} row(s) with an invalid code: {invalid[:5]}", file=sys.stderr)
        return 1

    written = write_category_map(args.out, merged)
    by_source: Dict[str, int] = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    weak = [row for row in rows
            if float(row.get("confidence") or 0) < 0.6 or row.get("source") == "repaired"]
    print(f"wrote {written} row(s) to {args.out} "
          f"({', '.join(f'{n} {source}' for source, n in sorted(by_source.items()))})")
    if weak:
        print(f"{len(weak)} leaf/leaves worth a look (repaired or low confidence):")
        for row in weak[:15]:
            print(f"  {float(row.get('confidence') or 0):.2f} {row['ncm_code']} {row['category_path']}")
    missing = [leaf.slug for leaf in taxonomy.leaves if leaf.slug not in {r['category_slug'] for r in merged}]
    if missing:
        print(f"{len(missing)} leaf/leaves left unmapped: {missing[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
