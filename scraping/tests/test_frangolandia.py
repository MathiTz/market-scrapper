"""Frangolândia's flyers: listed from its WordPress site, shown as images, no prices."""

import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from scraper.sites.frangolandia import FrangolandiaFlyers  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def wp_item(id, date, title="Ofertas &#8211; Horti"):
    return {"id": id, "date": date, "link": f"https://frangolandia.com/encarte/{id}/", "title": {"rendered": title}}


class TestFrangolandiaFlyers(unittest.TestCase):
    def setUp(self):
        self.page = (FIXTURES / "frangolandia_encarte.html").read_text(encoding="utf-8")

    def test_a_flyer_page_gives_only_its_own_gallery_images_in_order(self):
        self.assertEqual(FrangolandiaFlyers.parse_pages(self.page), [
            "https://frangolandia.com/wp-content/uploads/2026/09/PHOTO-2026-09-25-09-43-38.jpg",  # no logo, no thumbnail, no repeat
            "https://frangolandia.com/wp-content/uploads/2026/09/PHOTO-2026-09-25-09-43-45.jpg",
        ])

    def fetch(self, items, pages_html=None):
        def fetch_raw(url, params=None):
            return json.dumps(items) if "wp-json" in url else (self.page if pages_html is None else pages_html)

        with patch.object(FrangolandiaFlyers, "fetch_raw", side_effect=fetch_raw):
            return FrangolandiaFlyers().fetch_encartes(now=datetime(2026, 9, 27))

    def test_lists_recent_flyers_with_their_pages_and_a_clean_title(self):
        [flyer] = self.fetch([wp_item(1, "2026-09-26T12:00:22")])
        self.assertEqual((flyer.name, len(flyer.pages), flyer.posted_at[:10]), ("Ofertas – Horti", 2, "2026-09-26"))
        self.assertEqual(flyer.cover_url, flyer.pages[0])

    def test_a_flyer_older_than_two_weeks_is_left_out(self):
        self.assertEqual(self.fetch([wp_item(1, "2026-09-01T12:00:00")]), [])  # the site never removes old ones

    def test_a_flyer_page_with_no_images_is_left_out(self):
        self.assertEqual(self.fetch([wp_item(1, "2026-09-26T12:00:22")], pages_html="<html></html>"), [])

    def test_it_reads_no_prices(self):
        self.assertEqual(FrangolandiaFlyers().scrape(), [])


if __name__ == "__main__":
    unittest.main()
