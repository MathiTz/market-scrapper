"""The whole catalog of a Mercadapp storefront: categories, their subcategories and the pages of items."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from scraper import mercadapp  # noqa: E402
from scraper.base import ProductPrice  # noqa: E402
from scraper.sites.carnauba import CarnaubaScraper  # noqa: E402
from scraper.sites.mercadinho import MercadinhoScraper  # noqa: E402

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def item(item_id, name, price=5.0, **extra):
    return {"id": item_id, "description": name, "price": price, "original_price": price, "stock": 10,
            "offers": [], "bar_code": "", "image": "", **extra}


def page(*items):
    return {"mixes": [{"id": n, "items": [i]} for n, i in enumerate(items)]}


class FakeApi:
    """``get(path)`` as the page's session answers it: the shelves by category id, ``size`` items to a page."""

    def __init__(self, categories, subcategories, shelves, size=2, refuse=()):
        self.categories, self.subcategories, self.shelves, self.size, self.refuse = categories, subcategories, shelves, size, set(refuse)
        self.asked = []

    def __call__(self, path):
        self.asked.append(path)
        if path in self.refuse:
            return 403, None
        if path.endswith("/brand_categories"):
            return 200, {"categories": [{"id": c, "name": f"Cat {c}"} for c in self.categories]}
        if path.endswith("/subcategories"):
            category = int(path.split("/")[-2])
            return 200, {"subcategories": [{"id": s, "name": f"Sub {s}"} for s in self.subcategories.get(category, [])]}
        section, number = int(path.split("category_id=")[1]), int(path.split("page=")[1].split("&")[0])
        shelf = self.shelves.get(section, [])
        items = shelf[(number - 1) * self.size: number * self.size]
        return 200, {**page(*items), "has_next_page": number * self.size < len(shelf)}


class TestCatalogWalk(unittest.TestCase):
    def setUp(self):
        self.scraper = CarnaubaScraper()
        self.patch = patch.object(mercadapp, "PAUSE_SECONDS", 0)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def names(self, pages, **kwargs):
        return [p.product_name for p in self.scraper.parse_offers(pages, now=NOW, **kwargs)]

    def test_the_market_is_the_one_in_the_offers_address(self):
        self.assertEqual(CarnaubaScraper().market_id, "79")
        self.assertEqual(MercadinhoScraper().market_id, "355")

    def test_every_page_of_every_subcategory_is_read_and_a_category_with_none_is_read_as_itself(self):
        api = FakeApi(categories=[1, 2], subcategories={1: [11, 12]},
                      shelves={11: [item(1, "A"), item(2, "B"), item(3, "C")], 12: [item(4, "D")], 2: [item(5, "E"), item(6, "F")]})
        pages = self.scraper._walk_catalog(api, limit=100)
        self.assertEqual(self.names(pages), ["A", "B", "C", "D", "E", "F"])
        self.assertIn("v3/markets/79/items?page=2&limit=100&category_id=11", api.asked)
        self.assertIn("v3/markets/79/items?page=1&limit=100&category_id=2", api.asked)  # no subcategories: the category itself

    def test_a_product_on_several_shelves_counts_once_and_a_repeated_page_ends_the_shelf(self):
        class Repeating(FakeApi):
            def __call__(self, path):
                self.asked.append(path)
                if "page=" in path and "category_id=11" in path:
                    return 200, page(item(1, "A"))  # every page is the same
                self.asked.pop()
                return super().__call__(path)

        api = Repeating(categories=[1, 2], subcategories={1: [11]}, shelves={2: [item(1, "A"), item(2, "B")]})
        pages = self.scraper._walk_catalog(api, limit=100)
        self.assertEqual(self.names(pages), ["A", "B"])
        self.assertEqual(sum(1 for path in api.asked if "category_id=11" in path), 2)  # page 1 brought it, page 2 repeated

    def test_a_shelf_that_says_it_has_no_next_page_is_not_asked_for_another(self):
        api = FakeApi(categories=[1], subcategories={}, shelves={1: [item(1, "A"), item(2, "B")]}, size=2)
        self.scraper._walk_catalog(api, limit=100)
        self.assertEqual([p for p in api.asked if "items?" in p], ["v3/markets/79/items?page=1&limit=100&category_id=1"])

    def test_the_limit_stops_the_walk(self):
        api = FakeApi(categories=[1], subcategories={}, shelves={1: [item(n, f"P{n}") for n in range(1, 11)]})
        pages = self.scraper._walk_catalog(api, limit=3)
        self.assertEqual(len(self.names(pages, limit=3)), 3)
        self.assertLess(len(api.asked), 8)

    def test_a_refused_call_is_tried_again_and_a_dead_shelf_does_not_lose_the_others(self):
        api = FakeApi(categories=[1, 2], subcategories={}, shelves={1: [item(1, "A")], 2: [item(2, "B")]},
                      refuse=["v3/markets/79/items?page=1&limit=100&category_id=1"])
        with patch.object(mercadapp.time, "sleep"), self.assertLogs("scraper.mercadapp", level="WARNING"):
            pages = self.scraper._walk_catalog(api, limit=100)
        self.assertEqual(self.names(pages), ["B"])
        self.assertEqual(api.asked.count("v3/markets/79/items?page=1&limit=100&category_id=1"), len(mercadapp.BACKOFF_SECONDS) + 1)

    def test_no_categories_is_an_error_not_an_empty_catalog(self):
        with patch.object(mercadapp.time, "sleep"), self.assertRaises(RuntimeError):
            self.scraper._walk_catalog(FakeApi(categories=[], subcategories={}, shelves={}, refuse=["v2/markets/79/brand_categories"]), 100)

    def test_the_catalog_is_what_scrape_returns_and_the_offers_are_only_a_fallback(self):
        product = ProductPrice("Carnaúba Supermercados", "Arroz", 5.0, "u")
        with patch.object(CarnaubaScraper, "_scrape_catalog", return_value=[product]), \
                patch.object(CarnaubaScraper, "_scrape_json") as offers:
            self.assertEqual(self.scraper.scrape(), [product])
            offers.assert_not_called()

    def test_a_catalog_that_cannot_be_read_is_an_empty_list_for_the_fallback(self):
        with patch.object(CarnaubaScraper, "_create_driver", side_effect=RuntimeError("no chrome")):
            with self.assertLogs("scraper.mercadapp", level="WARNING"):
                self.assertEqual(self.scraper._scrape_catalog(100), [])


class TestLooseGoods(unittest.TestCase):
    def setUp(self):
        self.scraper = CarnaubaScraper()

    def parse(self, *items):
        return self.scraper.parse_offers([page(*items)], now=NOW)

    def test_loose_goods_are_priced_by_the_kilo_not_by_the_piece(self):
        avocado = item(1, "ABACATE", price=7.992, original_price=7.992, sold_in_kilogram=1, amount_in_kilo=0.8, kilogram_price=9.99)
        product = self.parse(avocado)[0]
        self.assertEqual((product.product_name, product.price, product.regular_price), ("ABACATE (kg)", 9.99, None))

    def test_a_name_that_already_says_kg_is_left_alone_and_a_discount_is_scaled_to_the_kilo(self):
        banana = item(2, "BANANA MACA KG", price=4.0, original_price=5.0, sold_in_kilogram=1, amount_in_kilo=0.5, kilogram_price=8.0)
        product = self.parse(banana)[0]
        self.assertEqual((product.product_name, product.price, product.regular_price), ("BANANA MACA KG", 8.0, 10.0))

    def test_a_packaged_product_keeps_its_price_rounded_to_cents(self):
        product = self.parse(item(3, "ARROZ 1KG", price=4.995, original_price=4.995, sold_in_kilogram=0, amount_in_kilo=None))[0]
        self.assertEqual((product.product_name, product.price), ("ARROZ 1KG", 5.0))


if __name__ == "__main__":
    unittest.main()
