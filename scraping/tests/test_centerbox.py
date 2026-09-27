"""Centerbox: prices from its Instabuy store's offers API, flyers from grupocenterbox.com.br."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from scraper.sites.centerbox import CenterboxScraper  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
HOME = '... {\\"storeData\\":{\\"store\\":{\\"id\\":\\"69d4fcef05d07daf70e2a599\\",\\"subdomain\\":\\"x\\"} ...'


class TestCenterboxPrices(unittest.TestCase):
    def setUp(self):
        self.items = json.loads((FIXTURES / "centerbox_offers.json").read_text(encoding="utf-8"))["data"]
        self.scraper = CenterboxScraper()

    def by_name(self, prefix):
        return next(p for p in map(self.scraper._to_product_price, self.items) if p and p.product_name.startswith(prefix))

    def test_a_promo_is_the_price_with_the_regular_price_and_percentage_off(self):
        oleo = self.by_name("Óleo")
        self.assertEqual((oleo.price, oleo.regular_price, oleo.offer), (8.79, 9.19, "4% OFF"))
        self.assertEqual((oleo.brand, oleo.url), ("Soya", "https://www.conceito.lojacenterbox.com.br/p/oleo-de-soja-soya-garrafa-900ml"))

    def test_a_club_price_is_the_price_and_the_everyone_price_is_its_regular_one(self):
        # the ETL serves a "Clube" deal label as two offers: what everyone pays, and the club price
        farinha = self.by_name("Farinha")
        self.assertEqual((farinha.price, farinha.regular_price, farinha.offer), (1.69, 1.89, "Clube CBOX"))

    def test_no_promo_is_just_the_regular_price(self):
        sabao = self.by_name("Sabão")
        self.assertEqual((sabao.price, sabao.regular_price, sabao.offer, sabao.image_url), (7.5, None, None, None))

    def test_a_weighed_item_says_kg_so_its_price_reads_as_per_kilo(self):
        self.assertEqual(self.by_name("Manga").product_name, "Manga Rosa Kg")

    def test_an_item_out_of_stock_is_left_out(self):
        self.assertIsNone(self.scraper._to_product_price(self.items[4]))

    def test_the_image_is_the_stores_medium_size(self):
        self.assertEqual(self.by_name("Farinha").image_url,
                         "https://assets.ibecom.com.br/ib.item.image.medium/m-3a58f5972f2846cbb81494b7998ff6a6.jpeg")

    def test_reads_every_page_until_an_empty_one_and_sends_the_stores_own_id(self):
        pages = [json.dumps({"data": self.items[:3]}), json.dumps({"data": self.items[3:]}), json.dumps({"data": []})]

        def fetch_raw(url, params=None):
            return HOME if params is None else pages[params["page"] - 1]

        scraper = CenterboxScraper()
        with patch.object(CenterboxScraper, "fetch_raw", side_effect=fetch_raw), patch("scraper.sites.centerbox.time.sleep"):
            products = scraper.scrape()
        self.assertEqual(len(products), 4)  # five items, one out of stock
        self.assertEqual(scraper.session.headers["x-store-id"], "69d4fcef05d07daf70e2a599")

    def test_no_store_id_in_the_home_page_is_a_failure_not_an_empty_scrape(self):
        with patch.object(CenterboxScraper, "fetch_raw", return_value="<html></html>"):
            with self.assertRaises(RuntimeError):
                CenterboxScraper().scrape()


class TestCenterboxFlyers(unittest.TestCase):
    def setUp(self):
        self.flyers = CenterboxScraper.parse_flyers((FIXTURES / "centerbox_ofertas.html").read_text(encoding="utf-8"))

    def test_only_this_weeks_flyers_are_listed_not_the_archive_below_them(self):
        self.assertEqual([f.name for f in self.flyers], ["Fim de Semana", "Yoki"])

    def test_front_and_back_are_one_flyer_with_two_pages(self):
        fim = self.flyers[0]
        self.assertEqual(len(fim.pages), 2)
        self.assertTrue(fim.pages[0].endswith("17.06.25.jpeg") and fim.pages[1].endswith("17.06.25-1.jpeg"))
        self.assertEqual(fim.cover_url, fim.pages[0])

    def test_the_posted_date_comes_from_the_image_file_name(self):
        self.assertEqual([f.posted_at[:10] for f in self.flyers], ["2026-09-22", "2026-09-24"])


if __name__ == "__main__":
    unittest.main()
