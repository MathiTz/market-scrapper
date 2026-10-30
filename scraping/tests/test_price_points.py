"""Tests for the price history synced to the cloud database."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite://"  # never touch the real market.db

from models import Price, PriceHistory, Product, SessionLocal, Store, init_db  # noqa: E402
from scraper.base import ProductPrice  # noqa: E402
from services.price_points import Series, collect, history_of, plan, product_key, sync  # noqa: E402
from services.scraper_service import save_scraped_results  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def at(days):
    return T0 + timedelta(days=days)


KEY = ("k", "Chain")


class TestPlan(unittest.TestCase):
    def test_the_first_sync_sends_the_archived_prices_and_the_current_one(self):
        series = {KEY: Series(archived=[(at(1), 500, None), (at(3), 450, None)], current=(at(5), 400, 600))}
        rows = plan(series, {})
        self.assertEqual([(r[2], r[3], r[4]) for r in rows], [(at(1), 500, None), (at(3), 450, None), (at(5), 400, 600)])

    def test_an_unchanged_price_adds_nothing_however_often_it_is_seen(self):
        series = {KEY: Series(current=(at(9), 400, None))}  # reconfirmed on day 9
        self.assertEqual(plan(series, {KEY: (at(5), 400)}), [])

    def test_a_changed_price_ends_the_old_stretch_and_starts_the_new(self):
        series = {KEY: Series(archived=[(at(7), 400, None)], current=(at(8), 380, None))}
        rows = plan(series, {KEY: (at(5), 400)})
        self.assertEqual([(r[2], r[3]) for r in rows], [(at(7), 400), (at(8), 380)])

    def test_a_return_to_the_old_price_between_two_syncs_is_not_lost(self):
        # A (known) -> B -> A again, and only now synced: B is archived, A is the current price.
        series = {KEY: Series(archived=[(at(6), 400, None), (at(7), 380, None)], current=(at(9), 400, None))}
        rows = plan(series, {KEY: (at(5), 400)})
        self.assertEqual([(r[2], r[3]) for r in rows], [(at(6), 400), (at(7), 380), (at(9), 400)])

    def test_archived_prices_neon_already_has_are_not_sent_again(self):
        series = {KEY: Series(archived=[(at(1), 500, None), (at(3), 450, None)], current=(at(5), 400, None))}
        rows = plan(series, {KEY: (at(5), 400)})
        self.assertEqual(rows, [])

    def test_a_pair_with_no_current_price_still_sends_its_archive(self):
        self.assertEqual(len(plan({KEY: Series(archived=[(at(1), 500, None)])}, {})), 1)

    def test_pairs_are_independent(self):
        series = {("a", "X"): Series(current=(at(1), 100, None)), ("a", "Y"): Series(current=(at(1), 100, None))}
        self.assertEqual(len(plan(series, {("a", "X"): (at(0), 100)})), 1)


class TestKey(unittest.TestCase):
    def test_case_does_not_change_the_key(self):
        self.assertEqual(product_key("Arroz TIPO 1 5kg"), product_key("arroz tipo 1 5kg"))
        self.assertNotEqual(product_key("Arroz 5kg"), product_key("Arroz 1kg"))


class TestCollectAndSync(unittest.TestCase):
    def setUp(self):
        init_db()
        self.addCleanup(self.wipe)  # the in-memory database is shared with the other test modules

    @staticmethod
    def wipe():
        db = SessionLocal()
        try:
            for model in (PriceHistory, Price, Product, Store):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def test_a_scraped_price_change_flows_into_points_and_a_second_sync_adds_nothing(self):
        name = "Feijao Preto Teste de Historico 1kg"
        save_scraped_results([ProductPrice(store_name="Loja Historico", product_name=name, price=8.0, url="u")])
        save_scraped_results([ProductPrice(store_name="Loja Historico", product_name=name, price=7.5, url="u")])
        db = SessionLocal()
        try:
            series = collect(db)[(product_key(name), "Loja Historico")]
            self.assertEqual([c for _, c, _ in series.archived], [800])
            self.assertEqual(series.current[1], 750)
            rows = plan({(product_key(name), "Loja Historico"): series}, {})
            self.assertEqual([r[3] for r in rows], [800, 750])
        finally:
            db.close()

    def test_history_of_answers_only_the_asked_products_grouped_by_chain(self):
        wanted, other = "Cafe Historico Pedido 500g", "Cafe Historico Outro 500g"
        for price in (9.0, 8.5):
            save_scraped_results([ProductPrice(store_name="Loja A", product_name=wanted, price=price, url="u")])
        save_scraped_results([ProductPrice(store_name="Loja B", product_name=wanted, price=9.9, url="u")])
        save_scraped_results([ProductPrice(store_name="Loja A", product_name=other, price=3.0, url="u")])
        db = SessionLocal()
        try:
            history = history_of(db, [product_key(wanted)])
        finally:
            db.close()
        self.assertEqual(list(history), [product_key(wanted)])
        chains = history[product_key(wanted)]
        self.assertEqual({chain: [cents for _, cents in points] for chain, points in chains.items()},
                         {"Loja A": [900, 850], "Loja B": [990]})
        self.assertEqual(chains["Loja A"], sorted(chains["Loja A"]))  # oldest first, ISO times
        self.assertTrue(chains["Loja A"][0][0].endswith("+00:00"))

    def test_sync_inserts_idempotently_and_dry_run_writes_nothing(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = []
        cursor = conn.cursor.return_value.__enter__.return_value
        connect = MagicMock(return_value=conn)
        db = SessionLocal()
        try:
            name = "Macarrao Teste Sync 500g"
            save_scraped_results([ProductPrice(store_name="Loja Sync", product_name=name, price=4.0, url="u")])
            self.assertGreaterEqual(sync("dsn", db, connect=connect, dry_run=True), 1)
            cursor.executemany.assert_not_called()
            self.assertGreaterEqual(sync("dsn", db, connect=connect), 1)
            sql = cursor.executemany.call_args.args[0]
            self.assertIn("ON CONFLICT DO NOTHING", sql)
        finally:
            db.close()


class TestPriceHistoryRoute(unittest.TestCase):
    def setUp(self):
        from local_api.app import app

        init_db()
        self.client = app.test_client()
        self.addCleanup(TestCollectAndSync.wipe)

    def test_it_returns_the_history_of_the_asked_keys(self):
        name = "Leite Historico Rota 1L"
        save_scraped_results([ProductPrice(store_name="Loja Rota", product_name=name, price=5.0, url="u")])
        res = self.client.get(f"/api/price-history?keys={product_key(name)},{'0' * 32}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("max-age", res.headers["Cache-Control"])
        history = res.get_json()["history"]
        self.assertEqual(list(history), [product_key(name)])  # a key with no points is left out
        self.assertEqual(history[product_key(name)]["Loja Rota"][0][1], 500)

    def test_bad_requests_are_refused(self):
        for query in ("", "?keys=", "?keys=not-a-key", f"?keys={'a' * 31}", "?keys=" + ",".join(["a" * 32] * 31)):
            self.assertEqual(self.client.get("/api/price-history" + query).status_code, 400, query)


if __name__ == "__main__":
    unittest.main()
