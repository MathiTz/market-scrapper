"""Analyze diagnostic results from the site scrapers.

Runs the updated (Scrapling-based) diagnosis, reads the JSON files,
and prints a summary of what was found on each site - including
whether products were extracted, any errors, and whether we're ready
to store data and show it on the web page.

Run:  python analyze_diagnostics.py
"""

import json
import sys
from pathlib import Path

from diagnose_sites import run_diagnosis, DIAG_DIR


def analyze() -> None:
    print("=" * 70)
    print("RUNNING UPDATED DIAGNOSIS (Scrapling-based)")
    print("=" * 70)
    files = run_diagnosis()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC ANALYSIS")
    print("=" * 70)

    all_ok = True
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        site_key = data["site_key"]
        site_name = data["site_name"]
        print(f"\n--- {site_name} ({site_key}) ---")

        # Homepage status
        hp = data.get("homepage") or {}
        hp_status = hp.get("status")
        hp_rendered = hp.get("rendered", False)
        hp_title = hp.get("title")
        hp_links = hp.get("links") or []
        hp_products = hp.get("product_elements") or []
        print(f"  Homepage: status={hp_status}, rendered={hp_rendered}, title={hp_title!r}")
        print(f"  Homepage links: {len(hp_links)}, product_elements: {len(hp_products)}")
        if hp_links:
            for link in hp_links[:5]:
                print(f"    -> {link['href']}  ({link['text'][:50]})")

        # Offers page
        op = data.get("offers_page") or {}
        if op.get("error"):
            print(f"  Offers page ERROR: {op['error']}")
            all_ok = False
        elif op:
            op_status = op.get("status")
            op_rendered = op.get("rendered", False)
            op_title = op.get("title")
            op_links = op.get("links") or []
            op_products = op.get("product_elements") or []
            print(f"  Offers page: status={op_status}, rendered={op_rendered}, title={op_title!r}")
            print(f"  Offers links: {len(op_links)}, product_elements: {len(op_products)}")
            if op_links:
                for link in op_links[:5]:
                    print(f"    -> {link['href']}  ({link['text'][:50]})")
        else:
            print("  No offers page configured")

        if data.get("error"):
            print(f"  Site-level ERROR: {data['error']}")
            all_ok = False

    print("\n" + "=" * 70)
    if all_ok:
        print("RESULT: All sites appear to be reachable. Products may be extractable.")
        print("We can proceed to store data and show it on the web page.")
    else:
        print("RESULT: There were errors on some sites. Review the output above.")
    print("=" * 70)


if __name__ == "__main__":
    analyze()
