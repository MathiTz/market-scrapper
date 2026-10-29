"""Tests for services/image_mirror.py - no network and no decision model needed."""

import io
import unittest
from unittest.mock import patch

from PIL import Image

from models import Product
from services import image_mirror as mirror


def an_image(width: int = 800, height: int = 600, colour=(200, 10, 10)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, "PNG")
    return buffer.getvalue()


def a_candidate(kind: str = "openfoodfacts", url: str = "https://example.test/a.jpg") -> mirror.Candidate:
    blob = an_image()
    return mirror.Candidate(kind, url, blob, mirror.prepare(blob))


def a_product(product_id: int = 1, name: str = "Requeijão Catupiry 200g", brand: str = "Catupiry",
              image_url=None) -> Product:
    return Product(id=product_id, name=name, brand=brand, gtin="7891234567890", image_url=image_url)


class PrepareTest(unittest.TestCase):
    def test_resizes_to_the_target_and_encodes_webp(self):
        webp, width, height = mirror.prepare(an_image(1200, 600))
        self.assertLessEqual(max(width, height), mirror.TARGET_PX)
        self.assertEqual((width, height), (400, 200))  # aspect ratio preserved
        self.assertEqual(Image.open(io.BytesIO(webp)).format, "WEBP")

    def test_rejects_an_image_too_small_to_be_a_product_photo(self):
        self.assertIsNone(mirror.prepare(an_image(60, 60)))

    def test_rejects_bytes_that_are_not_an_image(self):
        self.assertIsNone(mirror.prepare(b"<html>not an image</html>"))


class VerifyTest(unittest.TestCase):
    def test_accepts_only_when_every_criterion_passes(self):
        answers = {"is_package": {"noul": 0.99}, "is_product": {"noul": 0.95}, "is_brand": {"noul": 0.9}}
        with patch.object(mirror, "_ask_d3", return_value=answers):
            accepted, evidence = mirror.verify(a_product(), b"webp")
        self.assertTrue(accepted)
        self.assertEqual(set(evidence["scores"]), {"is_package", "is_product", "is_brand"})

    def test_rejects_when_the_brand_criterion_fails(self):
        answers = {"is_package": {"noul": 0.99}, "is_product": {"noul": 0.95}, "is_brand": {"noul": 0.2}}
        with patch.object(mirror, "_ask_d3", return_value=answers):
            accepted, evidence = mirror.verify(a_product(), b"webp")
        self.assertFalse(accepted)
        self.assertLess(evidence["scores"]["is_brand"], mirror.D3_THRESHOLD)

    def test_products_without_a_brand_are_not_asked_about_one(self):
        captured = {}

        def fake(questions, state, webp):
            captured.update(questions)
            return {name: {"noul": 0.99} for name in questions}

        with patch.object(mirror, "_ask_d3", side_effect=fake):
            accepted, _ = mirror.verify(a_product(brand=None), b"webp")
        self.assertTrue(accepted)
        self.assertNotIn("is_brand", captured)

    def test_a_missing_model_is_reported_as_an_error_not_a_rejection(self):
        with patch.object(mirror, "_ask_d3", return_value=None):
            accepted, evidence = mirror.verify(a_product(), b"webp")
        self.assertFalse(accepted)
        self.assertIn("error", evidence)


class MirrorProductTest(unittest.TestCase):
    def test_trusts_the_chain_image_without_calling_the_model(self):
        with patch.object(mirror, "fetch_bytes", return_value=an_image()), \
             patch.object(mirror, "verify") as verify:
            outcome = mirror.mirror_product(a_product(image_url="https://chain.test/x.jpg"), mirror._http())
        verify.assert_not_called()
        self.assertEqual((outcome.status, outcome.kind), ("ok", "chain"))

    def test_falls_through_to_a_lookup_when_the_chain_image_is_gone(self):
        candidate = a_candidate()
        with patch.object(mirror, "fetch_bytes", return_value=None), \
             patch.object(mirror, "openfoodfacts_candidates", return_value=iter([candidate])), \
             patch.object(mirror, "verify", return_value=(True, {"scores": {}})):
            outcome = mirror.mirror_product(a_product(image_url="https://chain.test/x.jpg"), mirror._http())
        self.assertEqual((outcome.status, outcome.kind), ("ok", "openfoodfacts"))

    def test_flags_after_three_rejected_candidates(self):
        candidates = [a_candidate(url=f"https://example.test/{n}.jpg") for n in range(4)]
        with patch.object(mirror, "fetch_bytes", return_value=None), \
             patch.object(mirror, "openfoodfacts_candidates", return_value=iter(candidates)), \
             patch.object(mirror, "verify", return_value=(False, {"scores": {"is_product": 0.1}})):
            outcome = mirror.mirror_product(a_product(), mirror._http())
        self.assertEqual(outcome.status, "flagged")
        self.assertEqual(outcome.decision["candidates"], mirror.MAX_WEB_CANDIDATES)

    def test_leaves_the_product_untouched_when_the_model_is_down(self):
        with patch.object(mirror, "fetch_bytes", return_value=None), \
             patch.object(mirror, "openfoodfacts_candidates", return_value=iter([a_candidate()])), \
             patch.object(mirror, "verify", return_value=(False, {"error": "decision model unavailable"})):
            outcome = mirror.mirror_product(a_product(), mirror._http())
        self.assertEqual(outcome.status, "skipped")

    def test_no_candidate_at_all_is_flagged(self):
        with patch.object(mirror, "fetch_bytes", return_value=None), \
             patch.object(mirror, "openfoodfacts_candidates", return_value=iter([])), \
             patch.object(mirror, "chain_search_candidates", return_value=iter([])), \
             patch.object(mirror, "web_search_candidates", return_value=iter([])):
            outcome = mirror.mirror_product(a_product(), mirror._http())
        self.assertEqual(outcome.status, "flagged")
        self.assertIn("no image", outcome.detail)


class WebSearchTest(unittest.TestCase):
    def test_vqd_is_read_from_the_landing_page(self):
        self.assertEqual(mirror._vqd('<a data-vqd="4-12345">'), "4-12345")
        self.assertIsNone(mirror._vqd("<html>nothing</html>"))

    def test_bing_results_are_unescaped(self):
        page = '<a murl&quot;:&quot;https://cdn.test/a.jpg&quot;></a><a murl&quot;:&quot;https://cdn.test/b.jpg&quot;></a>'

        class Response:
            status_code = 200
            text = page

        with patch.object(mirror.requests.Session, "get", return_value=Response()):
            self.assertEqual(mirror._bing_images("x", mirror._http(), 5),
                             ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"])


if __name__ == "__main__":
    unittest.main()
