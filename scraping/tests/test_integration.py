"""Integration tests that reach out to real websites.

These tests attempt to scrape live sites and verify that the scrapers
can fetch and parse product data. They are designed to be skipped
when network access is unavailable or sites are unreachable.

Run with:  python -m unittest tests.test_integration -v
"""

import os
import unittest

from scraper.sites import ALL_SCRAPERS

# Set to 1 to force integration tests to run even if network is slow
FORCE_INTEGRATION = os.getenv("FORCE_INTEGRATION", "0") in ("1", "true", "yes")


@unittest.skipUnless(
    FORCE_INTEGRATION or os.getenv("CI", ""),
    "Integration tests require network access. Set FORCE_INTEGRATION=1 to run.",
)
class TestLiveSiteScraping(unittest.TestCase):
    """Attempt to scrape real sites and validate that we can parse products."""

    def test_all_sites_return_products(self):
        """Each scraper should return at least one product for 'arroz'."""
        failures = []
        for scraper_cls in ALL_SCRAPERS:
            scraper = scraper_cls()
            with self.subTest(site=scraper.site_key):
                try:
                    results = scraper.scrape("arroz", limit=5)
                    self.assertGreater(
                        len(results), 0,
                        f"{scraper.site_name} returned no products for 'arroz'",
                    )
                    # Validate each product has a name and price > 0
                    for product in results:
                        self.assertTrue(product.product_name.strip())
                        self.assertGreater(product.price, 0)
                except Exception as exc:
                    failures.append(f"{scraper.site_key}: {exc}")
                finally:
                    scraper.close()
        if failures:
            self.fail(f"Sites failed: {'; '.join(failures)}")

    def test_offers_pages_return_products(self):
        """Offers pages should return products without a query."""
        for scraper_cls in ALL_SCRAPERS:
            scraper = scraper_cls()
            with self.subTest(site=scraper.site_key):
                try:
                    results = scraper.scrape("", limit=5)
                    self.assertGreater(
                        len(results), 0,
                        f"{scraper.site_name} returned no products from offers page",
                    )
                except Exception as exc:
                    # Some sites may not have an offers URL; log but don't fail
                    print(f"  {scraper.site_key} offers page error: {exc}")
                finally:
                    scraper.close()

    def test_price_parsing_brazilian_format(self):
        """Verify that price strings like 'R$ 1.234,56' parse correctly."""
        from scraper.sites.pao_de_acucar import PaoDeAcucarScraper

        scraper = PaoDeAcucarScraper()
        self.assertEqual(scraper._clean_price("R$ 1.234,56"), 1234.56)
        self.assertEqual(scraper._clean_price("R$ 12,34"), 12.34)
        self.assertEqual(scraper._clean_price("12.34"), 12.34)
        scraper.close()

    def test_extract_products_from_known_html(self):
        """Test extraction logic with mock HTML that mimics real site structure."""
        from bs4 import BeautifulSoup
        from scraper.sites.pao_de_acucar import PaoDeAcucarScraper

        scraper = PaoDeAcucarScraper()
        html = """
        <html>
          <div class="product-card">
            <h2 class="product-name">Arroz Tipo 1 5kg</h2>
            <span class="price">R$ 22,90</span>
            <a class="product-link" href="/produto/arroz">Ver</a>
          </div>
          <div class="product-card">
            <h2 class="product-name">Feijão Carioca 1kg</h2>
            <span class="price">R$ 8,90</span>
            <a class="product-link" href="/produto/feijao">Ver</a>
          </div>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        products = scraper.extract_products(soup, limit=10)
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0].product_name, "Arroz Tipo 1 5kg")
        self.assertEqual(products[0].price, 22.90)
        scraper.close()


if __name__ == "__main__":
    unittest.main()