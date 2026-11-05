"""Vendor the official NCM table into ``data/ncm/ncm.csv``.

The NCM is a closed list: a code either exists in the Receita's table or it does not, so the ETL
validates against a snapshot instead of trusting a model, and the warehouse never needs the network
to answer "is this code real".

BrasilAPI serves the table as JSON (the Receita's own CSV has a hostile encoding). This script keeps
every level - 2 (chapter), 4 (heading), 6 (subheading) and 8 (item) - normalises the code to digits
and the description to plain text, and drops the partial display nodes (``"0101.2"``) that are not a
level of the classification.

    python warehouse_ncm_fetch.py                       # fetch and write data/ncm/ncm.csv
    python warehouse_ncm_fetch.py --input ncm.json      # from a file already downloaded
    python warehouse_ncm_fetch.py --dry-run             # count without writing
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List

from warehouse import config
from warehouse.ncm import LEVELS, clean_text, normalize_code

SOURCE_URL = "https://brasilapi.com.br/api/ncm/v1"
HEADERS = ("code", "level", "chapter", "parent", "description")


def fetch(url: str = SOURCE_URL) -> List[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "mercado-em-dia/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def rows(raw: Iterable[dict]) -> List[dict]:
    """Normalise the API records into table rows, one per code, sorted by code.

    ``parent`` is the nearest *real* ancestor, not simply the code minus two digits: NCM has
    headings with a single "00" subheading and no 4-digit node of their own (``0504.00`` exists,
    ``0504`` does not), so the chain can skip a level. Walking up until a code exists keeps the
    column referentially sound whatever the Receita's tree does.
    """
    seen: Dict[str, dict] = {}
    for entry in raw:
        code = normalize_code(entry.get("codigo"))
        if code is None:
            continue
        description = clean_text(entry.get("descricao")).lstrip("-+ ").strip()
        if not description:
            continue
        seen.setdefault(code, {"code": code, "chapter": code[:2], "description": description})

    for code, row in seen.items():
        row["level"] = len(code)
        row["parent"] = ""
        for digits in (6, 4, 2):
            if digits < len(code) and code[:digits] in seen:
                row["parent"] = code[:digits]
                break
    return [seen[code] for code in sorted(seen)]


def write(path: Path, table: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(table)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, help="a JSON file already downloaded (skips the network)")
    parser.add_argument("--url", default=SOURCE_URL)
    parser.add_argument("--out", type=Path, default=config.NCM_TABLE_CSV)
    parser.add_argument("--dry-run", action="store_true", help="report the counts without writing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    raw = json.loads(args.input.read_text(encoding="utf-8")) if args.input else fetch(args.url)
    table = rows(raw)
    counts = {level: sum(1 for row in table if row["level"] == level) for level in LEVELS}
    print(f"{len(raw)} record(s) -> {len(table)} code(s): "
          + ", ".join(f"{counts[level]} x {level} digits" for level in LEVELS))
    if args.dry_run:
        return 0
    write(args.out, table)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
