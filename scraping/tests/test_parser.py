"""Tests for price parsing and HTML parsing helpers."""

import unittest

from scraper.base import BaseScraper, ProductPrice


class DummyScraper(BaseScraper):
    site_name = "dummy"
    base_url = "https://example.com"

    def scrape(self, query: str, limit: int = 20):
        return []


class TestPriceParsing(unittest.TestCase):
    def setUp(self):
        self.scraper = DummyScraper()

    def test_clean_price_comma(self):
        self.assertEqual(self.scraper._clean_price("R$ 12,34"), 12.34)

    def test_clean_price_dot(self):
        self.assertEqual(self.scraper._clean_price("12.34"), 12.34)

    def test_clean_price_thousands(self):
        self.assertEqual(self.scraper._clean_price("R$ 1.234,56"), 1234.56)

    def test_clean_price_empty(self):
        self.assertEqual(self.scraper._clean_price(""), 0.0)

    def test_clean_price_invalid(self):
        self.assertEqual(self.scraper._clean_price("abc"), 0.0)


if __name__ == "__main__":
    unittest.main()
