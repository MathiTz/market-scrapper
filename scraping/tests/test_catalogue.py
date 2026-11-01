"""Tests for the product catalogue synced to the cloud database."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite://"  # never touch the real market.db

from models import Price, PriceHistory, Product, SessionLocal, Store, init_db  # noqa: E402
from scraper.base import ProductPrice  # noqa: E402
from services.catalogue import collect, plan, sync  # noqa: E402
from services.price_points import product_key  # noqa: E402
from services.scraper_service import save_scraped_results  # noqa: E402

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def row(key="k", **over):
    base = dict(name="Arroz Tio Joao 1kg", brand="Tio Joao", category="Mercearia", subcategory="Arroz", amount=1000,
                unit="g", pack_count=1, gtin="7891234567895", image_url="http://x/i.png", first=T0,
                last=T0 + timedelta(days=3))
    base.update(over)
    return (key, *base.values())


def stored(r):
    return tuple(r[1:])


class TestPlan(unittest.TestCase):
    def test_a_product_neon_lacks_is_sent(self):
        self.assertEqual(plan([row()], {}), [row()])

    def test_an_identical_product_is_not_sent_again(self):
        self.assertEqual(plan([row()], {"k": stored(row())}), [])

    def test_a_source_that_gives_no_brand_barcode_or_photo_does_not_count_as_a_change(self):
        bare = row(brand=None, gtin=None, image_url=None)
        self.assertEqual(plan([bare], {"k": stored(row())}), [])

    def test_a_newly_found_barcode_is_sent(self):
        self.assertEqual(len(plan([row()], {"k": stored(row(gtin=None))})), 1)

    def test_last_seen_only_counts_when_a_day_or_more_later(self):
        later = row(last=row()[-1] + timedelta(hours=5))
        self.assertEqual(plan([later], {"k": stored(row())}), [])
        self.assertEqual(len(plan([row(last=row()[-1] + timedelta(days=2))], {"k": stored(row())})), 1)

    def test_first_seen_only_moves_earlier(self):
        self.assertEqual(len(plan([row(first=T0 - timedelta(days=9))], {"k": stored(row())})), 1)
        self.assertEqual(plan([row(first=T0 + timedelta(days=9))], {"k": stored(row())}), [])


class TestCollectAndSync(unittest.TestCase):
    def setUp(self):
        init_db()
        self.addCleanup(self.wipe)

    @staticmethod
    def wipe():
        db = SessionLocal()
        try:
            for model in (PriceHistory, Price, Product, Store):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def test_every_stored_product_is_collected_with_its_size_and_kind(self):
        save_scraped_results([ProductPrice(store_name="Loja Cat", product_name="Feijao Preto Catalogo 1kg", price=8.0, url="u",
                                           brand="Camil", gtin="7891234567895")])
        db = SessionLocal()
        try:
            [r] = [r for r in collect(db) if r[0] == product_key("Feijao Preto Catalogo 1kg")]
        finally:
            db.close()
        self.assertEqual((r[1], r[2], r[5], r[6], r[7], r[8]), ("Feijao Preto Catalogo 1kg", "Camil", 1000, "g", 1, "7891234567895"))
        self.assertLessEqual(r[10], r[11])

    def test_names_that_differ_only_in_case_are_one_product(self):
        for name in ("Cafe Caso Teste 500g", "CAFE CASO TESTE 500G"):
            save_scraped_results([ProductPrice(store_name="Loja Cat", product_name=name, price=9.0, url="u")])
        db = SessionLocal()
        try:
            self.assertEqual(len([r for r in collect(db) if r[0] == product_key("Cafe Caso Teste 500g")]), 1)
        finally:
            db.close()

    def test_sync_upserts_without_erasing_and_dry_run_writes_nothing(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.execute.return_value.fetchall.return_value = []
        cursor = conn.cursor.return_value.__enter__.return_value
        connect = MagicMock(return_value=conn)
        db = SessionLocal()
        try:
            save_scraped_results([ProductPrice(store_name="Loja Cat", product_name="Macarrao Catalogo 500g", price=4.0, url="u")])
            self.assertGreaterEqual(sync("dsn", db, connect=connect, dry_run=True), 1)
            cursor.executemany.assert_not_called()
            self.assertGreaterEqual(sync("dsn", db, connect=connect), 1)
            sql = cursor.executemany.call_args.args[0]
            self.assertIn("ON CONFLICT (product_key) DO UPDATE", sql)
            self.assertIn("COALESCE(EXCLUDED.gtin, products.gtin)", sql)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
