"""Tests for Flask web endpoints."""

import os
import unittest
from unittest.mock import patch

# Must be set before web.app imports config: never touch the real market.db.
os.environ["DATABASE_URL"] = "sqlite://"

from web.app import app  # noqa: E402


class TestWebEndpoints(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("status", data)
        self.assertIn("database", data)

    @patch("web.app.run_and_store")
    def test_scrape_with_query(self, mock_run_and_store):
        mock_run_and_store.return_value = 5
        resp = self.client.get("/scrape?query=arroz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["saved"], 5)

    @patch("web.app.run_all_offers")
    def test_scrape_offers(self, mock_run_all_offers):
        mock_run_all_offers.return_value = {"pao_de_acucar": 3}
        resp = self.client.get("/scrape")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["total"], 3)

    @patch("web.app.run_all_products")
    def test_scrape_all_products(self, mock_run_all_products):
        mock_run_all_products.return_value = 10
        resp = self.client.get("/scrape?mode=products")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["saved"], 10)

    @patch("web.app.run_all_offers")
    def test_scrape_no_query_runs_all_offers(self, mock_run_all_offers):
        """No query and no mode should scrape every site's offers page."""
        mock_run_all_offers.return_value = {"pao_de_acucar": 7}
        resp = self.client.get("/scrape")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["total"], 7)
        mock_run_all_offers.assert_called_once()

    def test_scrape_status_page(self):
        resp = self.client.get("/scrape/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), list)


if __name__ == "__main__":
    unittest.main()