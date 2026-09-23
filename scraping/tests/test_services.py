"""Tests for the scraper service layer."""

import os
import unittest
from unittest.mock import patch

# Must be set before the service imports config: never touch the real market.db.
os.environ["DATABASE_URL"] = "sqlite://"

from services.scraper_service import (  # noqa: E402
    HISTORY_CAP, append_history, pack_entry, run_and_store, run_all_products, run_all_offers, unpack_history,
)
from scraper.base import ProductPrice  # noqa: E402


class TestSaveDealDetails(unittest.TestCase):
    def test_regular_price_and_offer_label_are_stored(self):
        from models import Price, SessionLocal
        from services.scraper_service import save_scraped_results

        saved = save_scraped_results([ProductPrice(
            store_name="Cometa", product_name="Aveia NESTLÉ 170g", price=3.49, url="http://example.com",
            regular_price=5.15, offer="32% de desconto",
        )])
        self.assertEqual(saved, 1)
        db = SessionLocal()
        try:
            row = db.query(Price).order_by(Price.id.desc()).first()
            self.assertEqual((row.price, row.regular_price, row.offer), (3.49, 5.15, "32% de desconto"))
        finally:
            db.close()


class TestProductEnrichment(unittest.TestCase):
    """brand/gtin/image_url are filled in once and kept - see _get_or_create_product's own docstring."""

    def test_a_new_product_is_created_with_whatever_the_first_scrape_gives(self):
        from models import Product, SessionLocal
        from services.scraper_service import save_scraped_results

        save_scraped_results([ProductPrice(
            store_name="Atacadão", product_name="Achocolatado Nescau 400g", price=9.99, url="http://example.com",
            brand="Nestlé", gtin="7891000100103", image_url="http://img.example/nescau.jpg",
        )])
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.name == "Achocolatado Nescau 400g").one()
            self.assertEqual((product.brand, product.gtin, product.image_url),
                             ("Nestlé", "7891000100103", "http://img.example/nescau.jpg"))
        finally:
            db.close()

    def test_a_later_scrape_with_no_evidence_never_erases_what_an_earlier_one_found(self):
        from models import Product, SessionLocal
        from services.scraper_service import save_scraped_results

        save_scraped_results([ProductPrice(
            store_name="Atacadão", product_name="Achocolatado Nescau 400g", price=9.99, url="http://example.com",
            brand="Nestlé", gtin="7891000100103", image_url="http://img.example/nescau.jpg",
        )])
        # A different chain lists "the same" product by name but its source gives none of these.
        save_scraped_results([ProductPrice(
            store_name="Cometa", product_name="Achocolatado Nescau 400g", price=8.49, url="http://example.com",
        )])
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.name == "Achocolatado Nescau 400g").one()
            self.assertEqual((product.brand, product.gtin, product.image_url),
                             ("Nestlé", "7891000100103", "http://img.example/nescau.jpg"))
        finally:
            db.close()

    def test_a_later_scrape_can_still_fill_in_what_the_first_one_was_missing(self):
        from models import Product, SessionLocal
        from services.scraper_service import save_scraped_results

        save_scraped_results([ProductPrice(
            store_name="Cometa", product_name="Achocolatado Nescau 400g", price=8.49, url="http://example.com",
        )])
        save_scraped_results([ProductPrice(
            store_name="Atacadão", product_name="Achocolatado Nescau 400g", price=9.99, url="http://example.com",
            brand="Nestlé", gtin="7891000100103", image_url="http://img.example/nescau.jpg",
        )])
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.name == "Achocolatado Nescau 400g").one()
            self.assertEqual((product.brand, product.gtin, product.image_url),
                             ("Nestlé", "7891000100103", "http://img.example/nescau.jpg"))
        finally:
            db.close()


class TestPackedHistoryFormat(unittest.TestCase):
    def test_a_packed_entry_round_trips_through_unpack(self):
        from datetime import datetime, timezone

        when = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        packed = pack_entry(12.99, when)
        self.assertEqual(len(packed), 8)  # the whole point: fixed, tiny, not JSON
        [(cents, observed_at)] = unpack_history(packed)
        self.assertEqual((cents, observed_at), (1299, when))

    def test_appending_past_the_cap_drops_the_oldest_entries_first(self):
        from datetime import datetime, timezone

        blob = b""
        for day in range(1, HISTORY_CAP + 6):  # five more than the cap allows
            blob = append_history(blob, pack_entry(float(day), datetime(2026, 1, day, tzinfo=timezone.utc)))
        entries = unpack_history(blob)
        self.assertEqual(len(entries), HISTORY_CAP)  # never grows past the cap, however much is appended
        self.assertEqual([cents for cents, _ in entries], [d * 100 for d in range(6, HISTORY_CAP + 6)])  # oldest 5 gone


class TestPriceUpsert(unittest.TestCase):
    """One row per (product, store) in `prices`, not one row per scrape - see _upsert_price's own note."""

    def scrape(self, price, **kw):
        from services.scraper_service import save_scraped_results

        save_scraped_results([ProductPrice(
            store_name="Cometa", product_name="Requeijão Catupiry 200g", price=price,
            url="http://example.com", **kw,
        )])

    def row(self):
        from models import Price, SessionLocal

        db = SessionLocal()
        try:
            return db.query(Price).filter(Price.product_id == db.query(Price).first().product_id).all()
        finally:
            db.close()

    def test_a_repeated_scrape_at_the_same_price_stays_one_row(self):
        self.scrape(8.99)
        self.scrape(8.99)
        self.scrape(8.99)
        self.assertEqual(len(self.row()), 1)

    def test_a_scrape_at_a_new_price_still_stays_one_row_and_reflects_the_new_price(self):
        self.scrape(8.99)
        self.scrape(9.49)
        rows = self.row()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].price, 9.49)

    def test_a_price_change_is_archived_to_history_an_unchanged_one_is_not(self):
        from models import PriceHistory, SessionLocal

        self.scrape(8.99)
        self.scrape(8.99)  # confirmed again, unchanged: no history yet
        db = SessionLocal()
        try:
            self.assertIsNone(db.query(PriceHistory).first())
        finally:
            db.close()
        self.scrape(9.49)  # a real change: the old price is archived
        db = SessionLocal()
        try:
            history = db.query(PriceHistory).first()
            [(cents, _)] = unpack_history(history.blob)
            self.assertEqual(cents, 899)
        finally:
            db.close()


class TestScraperService(unittest.TestCase):
    @patch("services.scraper_service.save_scraped_results")
    @patch("services.scraper_service.ALL_SCRAPERS")
    @patch("services.scraper_service._record_attempt")
    def test_run_and_store_success(self, mock_record, mock_scrapers, mock_save):
        """Test run_and_store with a successful scraper."""
        mock_scraper = unittest.mock.Mock()
        mock_scraper.site_name = "Test Site"
        mock_scraper.site_key = "test_site"
        mock_scraper.scrape.return_value = [
            ProductPrice(
                store_name="Test",
                product_name="Arroz",
                price=10.0,
                url="http://example.com",
            )
        ]
        mock_scrapers.__iter__.return_value = [unittest.mock.Mock(return_value=mock_scraper)]
        mock_save.return_value = 1

        result = run_and_store("arroz", site=None)
        self.assertEqual(result, 1)
        mock_record.assert_called_once()
        args, kwargs = mock_record.call_args
        self.assertTrue(kwargs["success"])
        self.assertEqual(kwargs["items_found"], 1)

    @patch("services.scraper_service.save_scraped_results")
    @patch("services.scraper_service.ALL_SCRAPERS")
    @patch("services.scraper_service._record_attempt")
    def test_run_and_store_failure(self, mock_record, mock_scrapers, mock_save):
        """Test run_and_store with a failing scraper."""
        mock_scraper = unittest.mock.Mock()
        mock_scraper.site_name = "Test Site"
        mock_scraper.site_key = "test_site"
        mock_scraper.scrape.side_effect = RuntimeError("Network error")
        mock_scrapers.__iter__.return_value = [unittest.mock.Mock(return_value=mock_scraper)]

        result = run_and_store("arroz", site=None)
        self.assertEqual(result, 0)
        mock_record.assert_called_once()
        args, kwargs = mock_record.call_args
        self.assertFalse(kwargs["success"])
        self.assertIn("Network error", kwargs["error"])

    @patch("services.scraper_service.SessionLocal")
    def test_run_all_products_no_products(self, mock_session):
        """Test run_all_products with empty DB."""
        mock_db = unittest.mock.Mock()
        mock_db.query.return_value.all.return_value = []
        mock_session.return_value = mock_db

        result = run_all_products()
        self.assertEqual(result, 0)

    @patch("services.scraper_service.run_and_store")
    @patch("services.scraper_service.SessionLocal")
    def test_run_all_products_with_products(self, mock_session, mock_run_and_store):
        """Test run_all_products with products in DB."""
        mock_db = unittest.mock.Mock()
        product1 = unittest.mock.Mock()
        product1.name = "Arroz"
        product2 = unittest.mock.Mock()
        product2.name = "Feijao"
        mock_db.query.return_value.all.return_value = [product1, product2]
        mock_session.return_value = mock_db
        mock_run_and_store.return_value = 3

        result = run_all_products()
        self.assertEqual(result, 6)
        self.assertEqual(mock_run_and_store.call_count, 2)


if __name__ == "__main__":
    unittest.main()