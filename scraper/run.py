"""CLI entry point for running scrapers manually."""

import argparse
import logging
import os
import sys
from typing import List, Type

# Ensure project root is on sys.path so `import scraper` works
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Must come after sys.path setup
from scraper.base import BaseScraper
from scraper.sites import ALL_SCRAPERS, SCRAPER_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_site(scraper_cls: Type[BaseScraper], query: str, limit: int) -> None:
    """Run a single scraper for the given query."""
    scraper = scraper_cls()
    logger.info("Scraping %s for '%s'...", scraper.site_name, query or "ALL products")
    results = scraper.scrape(query, limit=limit)
    logger.info("Found %d results from %s", len(results), scraper.site_name)
    for r in results:
        logger.info("  - %s: R$ %.2f (%s)", r.product_name, r.price, r.url)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run market scrapers.")
    parser.add_argument("--site", choices=list(SCRAPER_MAP.keys()), help="Site to scrape")
    parser.add_argument("--all", action="store_true", help="Run all sites")
    parser.add_argument("--query", default="", help="Search query (empty = all products)")
    parser.add_argument("--limit", type=int, default=1000, help="Max results per site")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.all:
        for scraper_cls in ALL_SCRAPERS:
            run_site(scraper_cls, args.query, args.limit)
    elif args.site:
        scraper_cls = SCRAPER_MAP.get(args.site)
        if not scraper_cls:
            parser.error(f"Unknown site '{args.site}'. Available: {list(SCRAPER_MAP.keys())}")
        run_site(scraper_cls, args.query, args.limit)
    else:
        parser.error("Specify --site or --all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
