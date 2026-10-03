"""Tests for the product image backfill service.

No network and no real database: a fake HTTP session serves canned OFF payloads
and a fake SQLAlchemy session records what would be written.

Run with:  python -m unittest tests.test_image_enrichment -v
"""

import unittest

from services.image_enrichment import ProductImageEnricher, name_similarity


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeHTTP:
    """Maps URL substrings to responses; records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        return FakeResponse(None, status_code=404)


class FakeProduct:
    def __init__(self, id=1, name="Leite Ninho 380g", gtin=None, brand=None, image_url=None):
        self.id = id
        self.name = name
        self.gtin = gtin
        self.brand = brand
        self.image_url = image_url


class FakeQuery:
    def __init__(self, products):
        self._products = list(products)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._products = self._products[:n]
        return self

    def all(self):
        return self._products


class FakeSession:
    def __init__(self, products):
        self.products = list(products)
        self.commits = 0
        self.added = []

    def query(self, model):
        return FakeQuery(self.products)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


class NameSimilarityTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(name_similarity("Leite Ninho 380g", "Leite Ninho 380g"), 1.0)

    def test_word_order_insensitive(self):
        self.assertGreater(name_similarity("Leite Ninho 380g", "Ninho Leite 380g"), 0.9)

    def test_unrelated_is_low(self):
        self.assertLess(name_similarity("Leite Ninho 380g", "Detergente Ype 500ml"), 0.4)

    def test_empty_is_zero(self):
        self.assertEqual(name_similarity(None, "abc"), 0.0)
        self.assertEqual(name_similarity("abc", ""), 0.0)


class ResolveByGtinTests(unittest.TestCase):
    def test_hit_returns_full_confidence(self):
        http = FakeHTTP({
            "/api/v2/product/7891000315507.json": FakeResponse({
                "status": 1,
                "product": {"image_front_url": "https://img/off.jpg", "product_name": "Leite"},
            })
        })
        enricher = ProductImageEnricher(session=http)
        match = enricher.resolve_by_gtin("7891000315507")
        self.assertIsNotNone(match)
        self.assertEqual(match.image_url, "https://img/off.jpg")
        self.assertEqual(match.source, "gtin")
        self.assertEqual(match.confidence, 1.0)

    def test_missing_product_returns_none(self):
        http = FakeHTTP({"/api/v2/product/123.json": FakeResponse({"status": 0})})
        enricher = ProductImageEnricher(session=http)
        self.assertIsNone(enricher.resolve_by_gtin("123"))

    def test_non_numeric_gtin_skips_network(self):
        http = FakeHTTP({})
        enricher = ProductImageEnricher(session=http)
        self.assertIsNone(enricher.resolve_by_gtin("N/A"))
        self.assertEqual(http.calls, [])

    def test_network_error_returns_none(self):
        class Boom:
            headers = {}

            def get(self, *a, **k):
                raise RuntimeError("boom")

        enricher = ProductImageEnricher(session=Boom())
        self.assertIsNone(enricher.resolve_by_gtin("7891000315507"))


class ResolveBySearchTests(unittest.TestCase):
    def test_accepts_close_match(self):
        http = FakeHTTP({"/cgi/search.pl": FakeResponse({"products": [
            {"product_name": "Leite Ninho 380g", "image_front_url": "https://img/good.jpg"}
        ]})})
        enricher = ProductImageEnricher(session=http)
        match = enricher.resolve_by_search("Leite Ninho 380g")
        self.assertIsNotNone(match)
        self.assertEqual(match.image_url, "https://img/good.jpg")
        self.assertEqual(match.source, "search")
        self.assertGreater(match.confidence, 0.6)

    def test_rejects_weak_match(self):
        http = FakeHTTP({"/cgi/search.pl": FakeResponse({"products": [
            {"product_name": "Detergente Ype 500ml", "image_front_url": "https://img/wrong.jpg"}
        ]})})
        enricher = ProductImageEnricher(session=http)
        self.assertIsNone(enricher.resolve_by_search("Leite Ninho 380g"))

    def test_skips_candidates_without_image(self):
        http = FakeHTTP({"/cgi/search.pl": FakeResponse({"products": [
            {"product_name": "Leite Ninho 380g"}
        ]})})
        enricher = ProductImageEnricher(session=http)
        self.assertIsNone(enricher.resolve_by_search("Leite Ninho 380g"))


class EnrichProductTests(unittest.TestCase):
    def test_prefers_gtin_over_search(self):
        http = FakeHTTP({
            "/api/v2/product/789.json": FakeResponse(
                {"status": 1, "product": {"image_front_url": "https://img/gtin.jpg"}}),
            "/cgi/search.pl": FakeResponse({"products": [
                {"product_name": "x", "image_front_url": "https://img/search.jpg"}]}),
        })
        enricher = ProductImageEnricher(session=http)
        db = FakeSession([])
        product = FakeProduct(gtin="789", name="Leite Ninho 380g")
        result = enricher.enrich_product(db, product)
        self.assertTrue(result.updated)
        self.assertEqual(product.image_url, "https://img/gtin.jpg")
        self.assertEqual(result.source, "gtin")

    def test_never_overwrites_existing_image(self):
        http = FakeHTTP({})
        enricher = ProductImageEnricher(session=http)
        db = FakeSession([])
        product = FakeProduct(image_url="https://img/keep.jpg")
        result = enricher.enrich_product(db, product)
        self.assertFalse(result.updated)
        self.assertEqual(product.image_url, "https://img/keep.jpg")
        self.assertEqual(http.calls, [])

    def test_reports_no_match(self):
        http = FakeHTTP({})
        enricher = ProductImageEnricher(session=http)
        db = FakeSession([])
        result = enricher.enrich_product(db, FakeProduct(name="Leite Ninho 380g"))
        self.assertFalse(result.updated)
        self.assertEqual(result.reason, "no match found")


class EnrichMissingTests(unittest.TestCase):
    def test_fills_only_gap_products(self):
        http = FakeHTTP({"/api/v2/product/789.json": FakeResponse(
            {"status": 1, "product": {"image_front_url": "https://img/gtin.jpg"}})})
        enricher = ProductImageEnricher(session=http)
        have = FakeProduct(id=1, name="A", image_url="https://img/have.jpg")
        need = FakeProduct(id=2, name="B", gtin="789")
        db = FakeSession([have, need])
        results = enricher.enrich_missing(db, commit_every=1)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(r.updated for r in results), 1)
        self.assertEqual(need.image_url, "https://img/gtin.jpg")
        self.assertEqual(have.image_url, "https://img/have.jpg")
        self.assertGreaterEqual(db.commits, 1)

    def test_commits_in_batches(self):
        http = FakeHTTP({})
        enricher = ProductImageEnricher(session=http)
        db = FakeSession([FakeProduct(id=i, name=f"p{i}") for i in range(5)])
        enricher.enrich_missing(db, commit_every=2)
        # one commit per batch (2) plus the final flush
        self.assertEqual(db.commits, 3)

    def test_empty_id_list_does_nothing(self):
        http = FakeHTTP({})
        enricher = ProductImageEnricher(session=http)
        db = FakeSession([FakeProduct(id=1)])
        self.assertEqual(enricher.enrich_missing(db, only_ids=[]), [])
        self.assertEqual(http.calls, [])


if __name__ == "__main__":
    unittest.main()
