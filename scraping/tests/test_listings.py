"""The full-catalogue search's data: what every chain lists now (services/listings.py), and the snapshot cap."""

import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models import Base, Price, Product, ScrapeAttempt, Store  # noqa: E402
from services import listings, public_api  # noqa: E402
from services.price_points import product_key  # noqa: E402

NOW = datetime(2026, 11, 5, 12, 0)


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def attempt(db, key, run_id, items=1):
    db.add(ScrapeAttempt(site_key=key, run_id=run_id, success=True, items_found=items))
    db.flush()


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.db = make_db()
        self.addCleanup(self.db.close)
        self.carna = Store(name="Carnaúba Supermercados", website="https://c")
        self.atac = Store(name="Atacadão", website="https://a")
        self.db.add_all([self.carna, self.atac])
        self.db.flush()

    def price(self, store, product, price, run="r1", **kw):
        self.db.add(Price(product_id=product.id, store_id=store.id, price=price, run_id=run, scraped_at=NOW, **kw))

    def product(self, name):
        product = Product(name=name)
        self.db.add(product)
        self.db.flush()
        return product

    def test_each_product_and_chain_gets_the_price_it_lists_now_in_cents(self):
        rice = self.product("Arroz Camil 1kg")
        self.price(self.carna, rice, 5.49, regular_price=6.49, offer="15% OFF", url="https://c/arroz", stock=7)
        self.price(self.atac, rice, 4.99)
        self.db.commit()
        rows = {(r[0], r[1]): r for r in listings.collect(self.db)}
        key = product_key("Arroz Camil 1kg")
        self.assertEqual(rows[(key, "Carnaúba Supermercados")][3:7], (549, 649, "15% OFF", "https://c/arroz"))
        self.assertEqual(rows[(key, "Carnaúba Supermercados")][8], 7)
        self.assertEqual(rows[(key, "Atacadão")][3:6], (499, None, None))  # no discount: no regular price kept
        self.assertEqual(len(rows), 2)

    def test_a_price_that_is_not_on_the_chains_latest_run_is_no_longer_for_sale(self):
        gone, kept = self.product("Produto que saiu"), self.product("Produto que ficou")
        self.price(self.carna, gone, 3.0, run="old")
        self.price(self.carna, kept, 4.0, run="new")
        attempt(self.db, "carnauba", "old")
        attempt(self.db, "carnauba", "new")
        self.db.commit()
        with patch.object(public_api, "_site_keys", return_value={"Carnaúba Supermercados": "carnauba"}):
            names = {r[0] for r in listings.collect(self.db)}
        self.assertEqual(names, {product_key("Produto que ficou")})

    def test_names_that_differ_only_in_case_are_one_listing_with_the_newest_price(self):
        first, second = self.product("Leite Integral 1l"), self.product("LEITE INTEGRAL 1L")
        self.price(self.carna, first, 4.0)
        self.price(self.carna, second, 4.5)
        self.db.commit()
        rows = listings.collect(self.db)
        self.assertEqual([(r[1], r[3]) for r in rows], [("Carnaúba Supermercados", 450)])

    def test_the_name_is_stored_as_the_app_shows_it(self):
        self.price(self.carna, self.product("ARROZ CAMIL TIPO 1 5KG"), 25.0)
        self.db.commit()
        self.assertEqual(listings.collect(self.db)[0][2], "Arroz Camil Tipo 1 5kg")

    def test_unusable_prices_are_left_out(self):
        self.price(self.carna, self.product("Sem preço"), 0.0)
        self.db.commit()
        self.assertEqual(listings.collect(self.db), [])


class TestSync(unittest.TestCase):
    def connection(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        self.copied = []
        copy = cursor.copy.return_value.__enter__.return_value
        copy.write_row.side_effect = self.copied.append
        return conn, cursor

    def test_the_table_is_replaced_in_one_transaction(self):
        db = make_db()
        self.addCleanup(db.close)
        store = Store(name="Atacadão")
        product = Product(name="Arroz")
        db.add_all([store, product])
        db.flush()
        db.add(Price(product_id=product.id, store_id=store.id, price=5.0, run_id="r", scraped_at=NOW))
        db.commit()
        conn, cursor = self.connection()
        self.assertEqual(listings.sync("dsn", db, connect=MagicMock(return_value=conn)), 1)
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(sql, ["DELETE FROM current_prices"])
        self.assertEqual(len(self.copied), 1)
        self.assertEqual(self.copied[0][:4], (product_key("Arroz"), "Atacadão", "Arroz", 500))

    def test_a_run_that_lists_nothing_does_not_empty_the_table(self):
        connect = MagicMock()
        with self.assertLogs("services.listings", level="WARNING"):
            db = make_db()
            self.addCleanup(db.close)
            self.assertEqual(listings.sync("dsn", db, connect=connect), 0)
        connect.assert_not_called()

    def test_a_dry_run_writes_nothing(self):
        db = make_db()
        self.addCleanup(db.close)
        store, product = Store(name="Atacadão"), Product(name="Arroz")
        db.add_all([store, product])
        db.flush()
        db.add(Price(product_id=product.id, store_id=store.id, price=5.0, run_id="r", scraped_at=NOW))
        db.commit()
        connect = MagicMock()
        self.assertEqual(listings.sync("dsn", db, connect=connect, dry_run=True), 1)
        connect.assert_not_called()


def price(offer=None, regular=None, value=5.0):
    return SimpleNamespace(offer=offer, regular_price=regular, price=value)


class TestSnapshotCap(unittest.TestCase):
    def test_zero_keeps_everything(self):
        merged = {(n, 1): price() for n in range(5)}
        self.assertEqual(public_api.most_useful(merged, 0), merged)

    def test_discounts_come_first_then_products_several_chains_sell_then_the_rest(self):
        merged = {
            (1, 1): price(),                       # plain, one chain
            (2, 1): price(),                       # plain, sold by two chains
            (2, 2): price(),
            (3, 1): price(regular=7.0),            # discounted
            (4, 1): price(offer="Leve 3 pague 2"),  # a deal
        }
        kept = public_api.most_useful(merged, 3)
        self.assertEqual(set(kept), {(3, 1), (4, 1), (2, 1), (2, 2)})  # chain 2 has one product: under its cap

    def test_the_cap_applies_to_each_chain_on_its_own(self):
        merged = {(n, 1): price() for n in range(4)} | {(n, 2): price() for n in range(10, 12)}
        kept = public_api.most_useful(merged, 2)
        self.assertEqual(sum(1 for _, r in kept if r == 1), 2)
        self.assertEqual(sum(1 for _, r in kept if r == 2), 2)

    def test_the_same_data_always_picks_the_same_products(self):
        merged = {(n, 1): price() for n in range(20)}
        self.assertEqual(list(public_api.most_useful(merged, 5)), list(public_api.most_useful(dict(reversed(list(merged.items()))), 5)))


class TestSnapshotWithCap(unittest.TestCase):
    def test_the_snapshot_carries_only_the_capped_products_and_says_so_in_its_coverage(self):
        db = make_db()
        self.addCleanup(db.close)
        store = Store(name="Atacadão", website="https://a")
        db.add(store)
        db.flush()
        for name, price, regular in [("Arroz Camil 1kg", 5.0, None), ("Feijão Kicaldo 1kg", 7.0, 9.0), ("Açúcar União 1kg", 4.0, None)]:
            product = Product(name=name)
            db.add(product)
            db.flush()
            db.add(Price(product_id=product.id, store_id=store.id, price=price, regular_price=regular, run_id="r", scraped_at=NOW))
        db.commit()
        with patch.object(public_api.config, "SNAPSHOT_OFFERS_PER_CHAIN", 2):
            data = public_api.build_public(db, encartes=[])
        self.assertEqual(len(data["offers"]), 2)
        self.assertEqual(len(data["products"]), 2)  # a product with no offer left is not shipped
        self.assertEqual(data["coverage"]["offers"], 2)
        self.assertIn("Feijão Kicaldo 1kg", {p["name"] for p in data["products"]})  # the discounted one is kept
        with patch.object(public_api.config, "SNAPSHOT_OFFERS_PER_CHAIN", 0):
            self.assertEqual(len(public_api.build_public(db, encartes=[])["offers"]), 3)


if __name__ == "__main__":
    unittest.main()
