"""GBarbosa (VTEX): prices from the product search, one subcategory at a time."""

import json
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from scraper.sites import SCRAPER_MAP  # noqa: E402
from scraper.sites.gbarbosa import GBarbosaScraper  # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures" / "gbarbosa_products.json").read_text(encoding="utf-8")

TREE = json.dumps([
    {"name": "Mercearia", "url": "https://www.gbarbosa.com.br/mercearia", "children": [
        {"name": "Temperos", "url": "https://www.gbarbosa.com.br/mercearia/temperos"},
        {"name": "Molhos", "url": "https://www.gbarbosa.com.br/mercearia/molhos-e-condimentos"},
    ]},
    {"name": "Peixaria", "url": "https://www.gbarbosa.com.br/peixaria", "children": []},
    {"name": "Eletro", "url": "https://www.gbarbosa.com.br/eletro", "children": [
        {"name": "TVs", "url": "https://www.gbarbosa.com.br/eletro/tvs"},
    ]},
])


class TestGBarbosa(unittest.TestCase):
    def setUp(self):
        self.scraper = GBarbosaScraper()
        self.scraper.categories = ("mercearia", "peixaria")  # the real list has eleven; two cover both shapes

    def test_it_is_registered_under_its_key(self):
        self.assertIs(SCRAPER_MAP["gbarbosa"], GBarbosaScraper)

    def test_a_department_is_read_by_subcategory_and_a_department_without_any_whole(self):
        with patch.object(GBarbosaScraper, "fetch_raw", return_value=TREE):
            self.assertEqual(self.scraper._category_paths(), [
                "mercearia/category-2/temperos", "mercearia/category-2/molhos-e-condimentos", "peixaria",
            ])  # "eletro" is not in categories, so it is never read

    def test_a_category_tree_that_cannot_be_read_falls_back_to_whole_departments(self):
        with patch.object(GBarbosaScraper, "fetch_raw", side_effect=RuntimeError("down")):
            with self.assertLogs("scraper.vtex", level=logging.WARNING):
                self.assertEqual(self.scraper._category_paths(), ["mercearia", "peixaria"])

    def test_scrape_asks_for_each_subcategory_and_keeps_every_product_once(self):
        asked = []

        def fetch_raw(url, params=None):
            if "category/tree" in url:
                return TREE
            asked.append(url.split("/product_search/")[1])
            # the same three products in every subcategory: a product listed twice is one offer
            return FIXTURE if params["page"] == 1 else json.dumps({"products": []})

        with patch.object(GBarbosaScraper, "fetch_raw", side_effect=fetch_raw):
            offers = self.scraper.scrape()
        self.assertEqual(asked, ["category-1/mercearia/category-2/temperos", "category-1/mercearia/category-2/molhos-e-condimentos",
                                 "category-1/peixaria"])
        self.assertEqual(len(offers), 3)

    def test_the_price_the_list_price_and_the_barcode_are_read(self):
        with patch.object(GBarbosaScraper, "fetch_raw", return_value=FIXTURE):
            offers = self.scraper._category_offers("mercearia/category-2/temperos", cap=100)
        by_name = {o.product_name: o for o in offers}
        plain = by_name["Sal Refinado Globo"]
        self.assertEqual((plain.price, plain.regular_price, plain.offer, plain.store_name), (2.69, None, None, "GBarbosa"))
        self.assertTrue(plain.url.startswith("https://www.gbarbosa.com.br/") and plain.url.endswith("/p"))
        self.assertEqual(plain.gtin, "7896029310014")
        self.assertIsNone(plain.stock)  # 10,000 is how VTEX says "not tracked"
        azeite = next(o for n, o in by_name.items() if n.startswith("Azeite"))
        self.assertEqual((azeite.price, azeite.regular_price, azeite.offer), (28.9, 35.99, "20% OFF"))


if __name__ == "__main__":
    unittest.main()
