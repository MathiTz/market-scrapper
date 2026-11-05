"""GET /api/search over the local database: the whole catalogue, ranked, one entry per product."""

import os
import unittest
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models import Base, Price, Product, Store  # noqa: E402
from services import catalogue_search as cs  # noqa: E402
from services.price_points import product_key  # noqa: E402

NOW = datetime(2026, 11, 5, 12, 0)


class TestWords(unittest.TestCase):
    def test_accents_case_and_punctuation_are_ignored(self):
        self.assertEqual(cs.words_of("  Feijão-Preto  1KG "), ["feijao", "preto", "1kg"])

    def test_a_query_too_short_or_too_long_is_unusable(self):
        self.assertEqual(cs.words_of("a"), [])
        self.assertEqual(cs.words_of("x" * 61), [])
        self.assertEqual(cs.words_of(""), [])

    def test_every_typed_word_must_start_a_word_of_the_text_in_any_order(self):
        self.assertTrue(cs.matches("Abacaxi Pérola Unidade", ["unid", "aba"]))
        self.assertFalse(cs.matches("Abacaxi Pérola Unidade", ["baca"]))  # a prefix, not a substring


class TestSearch(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        self.a, self.b = Store(name="Atacadão"), Store(name="GBarbosa")
        self.db.add_all([self.a, self.b])
        self.db.flush()

    def stock(self, store, name, price, brand=None, **kw):
        product = self.db.query(Product).filter(Product.name == name).first()
        if product is None:
            product = Product(name=name, brand=brand)
            self.db.add(product)
            self.db.flush()
        self.db.add(Price(product_id=product.id, store_id=store.id, price=price, run_id="r", scraped_at=NOW, **kw))
        self.db.commit()

    def test_a_product_comes_with_the_price_at_every_chain_that_lists_it(self):
        self.stock(self.a, "Arroz Camil Branco 1kg", 5.49, brand="Camil")
        self.stock(self.b, "Arroz Camil Branco 1kg", 4.99, regular_price=5.99, offer="17% OFF")
        body = cs.search(self.db, "arroz camil")
        self.assertEqual(len(body["results"]), 1)
        item = body["results"][0]
        self.assertEqual((item["key"], item["brand"], item["amount"], item["unit"]),
                         (product_key("Arroz Camil Branco 1kg"), "Camil", 1000, "g"))
        prices = {p["store"]: p for p in item["prices"]}
        self.assertEqual(prices["Atacadão"]["price_cents"], 549)
        self.assertEqual((prices["GBarbosa"]["price_cents"], prices["GBarbosa"]["regular_price_cents"], prices["GBarbosa"]["deal_label"]),
                         (499, 599, "17% OFF"))

    def test_the_brand_is_searched_too(self):
        self.stock(self.a, "Feijão Carioca 1kg", 7.0, brand="Kicaldo")
        self.assertEqual(len(cs.search(self.db, "kicaldo feijao")["results"]), 1)

    def test_names_starting_with_what_was_typed_come_first_then_the_shorter(self):
        self.stock(self.a, "Biscoito de Leite Condensado 100g", 3.0)
        self.stock(self.a, "Leite Integral Italac 1l", 5.0)
        self.stock(self.a, "Leite 1l", 4.5)
        names = [r["name"] for r in cs.search(self.db, "leite")["results"]]
        self.assertEqual(names, ["Leite 1l", "Leite Integral Italac 1l", "Biscoito de Leite Condensado 100g"])

    def test_the_limit_truncates_and_says_so(self):
        for n in range(5):
            self.stock(self.a, f"Suco de Uva {n}", 4.0)
        body = cs.search(self.db, "suco", limit=3)
        self.assertEqual((len(body["results"]), body["truncated"]), (3, True))
        self.assertFalse(cs.search(self.db, "suco", limit=10)["truncated"])

    def test_nothing_found_is_an_empty_list_and_an_unusable_query_is_none(self):
        self.stock(self.a, "Arroz", 5.0)
        self.assertEqual(cs.search(self.db, "zzzz"), {"results": [], "truncated": False})
        self.assertIsNone(cs.search(self.db, "a"))


class TestRoute(unittest.TestCase):
    def test_the_flask_route_answers_the_same_body_and_rejects_a_short_query(self):
        from unittest.mock import patch

        from local_api import app as flask_app

        body = {"results": [], "truncated": False}
        client = flask_app.app.test_client()
        with patch.object(flask_app.catalogue_search, "search", return_value=body) as search, \
                patch.object(flask_app, "get_db"):
            ok = client.get("/api/search?q=arroz&limit=5")
            self.assertEqual((ok.status_code, ok.get_json()), (200, body))
            self.assertEqual(search.call_args.args[1:], ("arroz", 5))
            search.return_value = None
            self.assertEqual(client.get("/api/search?q=a").status_code, 400)


if __name__ == "__main__":
    unittest.main()
