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


class TestSameStoreListingsOfOneProduct(unittest.TestCase):
    """A store that lists one product name several times (Centerbox keeps a sandal under three listings, at
    9,99, 14,99 and 9,99) is still one (product, store). The session does not autoflush, so a second upsert of
    the same key used to miss the first one's pending rows: a second `prices` row, or a second `price_history`
    row - a primary-key error that aborted the whole save."""

    def listings(self, name, *prices, store="Centerbox", **kw):
        from services.scraper_service import save_scraped_results

        return save_scraped_results([
            ProductPrice(store_name=store, product_name=name, price=price, url=f"http://example.com/{index}", **kw)
            for index, price in enumerate(prices)
        ])

    def stored(self, name):
        from models import Price, PriceHistory, Product, SessionLocal

        db = SessionLocal()
        try:
            ids = [p.id for p in db.query(Product).filter(Product.name == name)]
            prices = db.query(Price).filter(Price.product_id.in_(ids)).all() if ids else []
            history = db.query(PriceHistory).filter(PriceHistory.product_id.in_(ids)).all() if ids else []
            return ids, prices, history
        finally:
            db.close()

    def test_a_new_product_listed_three_times_is_one_row_at_the_lowest_price(self):
        saved = self.listings("Chinelo Aloha Teste A", 9.99, 14.99, 9.99)
        _, prices, _ = self.stored("Chinelo Aloha Teste A")
        self.assertEqual([p.price for p in prices], [9.99])
        self.assertEqual(saved, 1)  # distinct prices saved, not listings read

    def test_the_price_kept_does_not_depend_on_the_order_the_store_returns_them_in(self):
        self.listings("Chinelo Aloha Teste B", 14.99, 9.99)
        self.listings("Chinelo Aloha Teste C", 9.99, 14.99)
        for name in ("Chinelo Aloha Teste B", "Chinelo Aloha Teste C"):
            _, prices, _ = self.stored(name)
            self.assertEqual([p.price for p in prices], [9.99], name)

    def test_a_known_product_listed_twice_at_changed_prices_no_longer_aborts_the_save(self):
        # The exact failure: the stored price differs from both listings, so each wanted a history row.
        self.listings("Chinelo Aloha Teste D", 20.00)
        self.listings("Chinelo Aloha Teste D", 9.99, 14.99)  # raised IntegrityError before
        _, prices, history = self.stored("Chinelo Aloha Teste D")
        self.assertEqual([p.price for p in prices], [9.99])
        self.assertEqual(len(history), 1)
        self.assertEqual([cents for cents, _ in unpack_history(history[0].blob)], [2000])  # the old price, once

    def test_the_kept_listing_brings_its_own_regular_price_offer_and_url(self):
        from services.scraper_service import save_scraped_results

        save_scraped_results([
            ProductPrice(store_name="Centerbox", product_name="Chinelo Aloha Teste E", price=14.99,
                         regular_price=21.99, offer="32% OFF", url="http://example.com/dear"),
            ProductPrice(store_name="Centerbox", product_name="Chinelo Aloha Teste E", price=9.99,
                         regular_price=12.99, offer="23% OFF", url="http://example.com/cheap"),
        ])
        [price] = self.stored("Chinelo Aloha Teste E")[1]
        self.assertEqual((price.price, price.regular_price, price.offer, price.url),
                         (9.99, 12.99, "23% OFF", "http://example.com/cheap"))

    def test_the_same_name_at_two_stores_stays_two_rows(self):
        self.listings("Chinelo Aloha Teste F", 9.99, store="Centerbox")
        self.listings("Chinelo Aloha Teste F", 12.50, store="Atacadão")
        _, prices, _ = self.stored("Chinelo Aloha Teste F")
        self.assertEqual(sorted(p.price for p in prices), [9.99, 12.5])

    def test_duplicate_rows_left_by_the_old_behaviour_are_collapsed_on_the_next_save(self):
        from models import Price, Product, SessionLocal, Store

        self.listings("Chinelo Aloha Teste G", 9.99)
        ids, [row], _ = self.stored("Chinelo Aloha Teste G")
        db = SessionLocal()
        try:  # what a run before this fix could leave: a second row for the same (product, store)
            db.add(Price(product_id=row.product_id, store_id=row.store_id, price=14.99, url="http://example.com/old"))
            db.commit()
        finally:
            db.close()
        self.assertEqual(len(self.stored("Chinelo Aloha Teste G")[1]), 2)
        self.listings("Chinelo Aloha Teste G", 9.49)
        _, prices, _ = self.stored("Chinelo Aloha Teste G")
        self.assertEqual([p.price for p in prices], [9.49])

    def test_percent_signs_in_a_name_do_not_merge_it_with_a_different_product(self):
        # "%" is a LIKE wildcard: looking up "...0% Gordura..." used to match the existing "...0,5% Gordura...",
        # so one product swallowed the other (and took its price). The longer name has to exist first.
        self.listings("Iogurte Natural 0,5% Gordura 170g Teste", 3.90)
        self.listings("Iogurte Natural 0% Gordura 170g Teste", 3.50)
        first, second = (self.stored(n) for n in ("Iogurte Natural 0% Gordura 170g Teste",
                                                  "Iogurte Natural 0,5% Gordura 170g Teste"))
        self.assertEqual([p.price for p in first[1]], [3.50])
        self.assertEqual([p.price for p in second[1]], [3.90])
        self.assertNotEqual(first[0], second[0])

    def test_a_name_still_resolves_case_insensitively_and_an_underscore_is_not_a_wildcard(self):
        self.listings("paoXde_forma teste 500g", 3.00)  # exists first...
        self.listings("pao_de_forma teste 500g", 1.00)  # ..."_" would have matched its X: a different product
        self.listings("PAO_DE_FORMA TESTE 500G", 2.00)  # the same product as the line above, in capitals
        from models import Product, SessionLocal

        db = SessionLocal()
        try:
            names = sorted(p.name for p in db.query(Product).filter(Product.name.ilike("pao%de%forma teste 500g")))
        finally:
            db.close()
        self.assertEqual(set(names), {"pao_de_forma teste 500g", "paoXde_forma teste 500g"})
        self.assertEqual(len(names), 2)
        self.assertEqual([p.price for p in self.stored("pao_de_forma teste 500g")[1]], [2.00])


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