"""Tests for the image health cache and the mirror fallback in the payload."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import image_health
from services.public_api import _public_image


class CacheTest(unittest.TestCase):
    def setUp(self):
        image_health._CACHE.update(stamp=None, entries={})
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "image-health.json"

    def test_a_missing_cache_means_no_opinion(self):
        self.assertEqual(image_health.load(self.path), {})
        self.assertFalse(image_health.is_dead("https://cdn.loja.com.br/a.jpg"))

    def test_round_trip(self):
        image_health.save({"https://cdn.loja.com.br/a.jpg": {"ok": False, "at": "2026-11-05T00:00:00Z"}}, self.path)
        self.assertEqual(image_health.load(self.path)["https://cdn.loja.com.br/a.jpg"]["ok"], False)

    def test_only_a_definite_failure_is_dead(self):
        entries = {
            "https://cdn.loja.com.br/dead.jpg": {"ok": False, "at": "2026-11-05T00:00:00Z"},
            "https://cdn.loja.com.br/unsure.jpg": {"ok": None, "at": "2026-11-05T00:00:00Z"},
            "https://cdn.loja.com.br/ok.jpg": {"ok": True, "at": "2026-11-05T00:00:00Z"},
        }
        self.assertTrue(image_health.is_dead("https://cdn.loja.com.br/dead.jpg", entries))
        self.assertFalse(image_health.is_dead("https://cdn.loja.com.br/unsure.jpg", entries))
        self.assertFalse(image_health.is_dead("https://cdn.loja.com.br/ok.jpg", entries))
        self.assertFalse(image_health.is_dead("https://cdn.loja.com.br/new.jpg", entries))
        self.assertFalse(image_health.is_dead(None, entries))

    def test_an_unsure_answer_is_retried_soon_and_a_definite_one_weekly(self):
        self.assertTrue(image_health._is_stale({"ok": None, "at": "2000-01-01T00:00:00Z"}))
        self.assertTrue(image_health._is_stale({"ok": True, "at": "2000-01-01T00:00:00Z"}))
        self.assertFalse(image_health._is_stale({"ok": True, "at": image_health._now().strftime("%Y-%m-%dT%H:%M:%SZ")}))
        self.assertTrue(image_health._is_stale(None))

    def test_refresh_keeps_what_it_knows_and_checks_the_rest(self):
        image_health.save({"https://cdn.loja.com.br/old.jpg": {"ok": True, "at": "2026-11-05T00:00:00Z"}}, self.path)
        with patch.object(image_health, "check", side_effect=lambda url: url.endswith("/dead.jpg") is False):
            entries = image_health.refresh(
                ["https://cdn.loja.com.br/old.jpg", "https://cdn.loja.com.br/dead.jpg", "not-a-url"], path=self.path)
        self.assertTrue(entries["https://cdn.loja.com.br/old.jpg"]["ok"])
        self.assertFalse(entries["https://cdn.loja.com.br/dead.jpg"]["ok"])
        self.assertNotIn("not-a-url", entries)

    def test_a_placeholder_host_is_never_an_image(self):
        # A test fixture once wrote http://img.example/nescau.jpg into market.db; documentation hosts
        # must never reach the payload, whatever the cache says.
        self.assertTrue(image_health.is_placeholder("http://img.example/nescau.jpg"))
        self.assertTrue(image_health.is_placeholder("https://example.com/a.jpg"))
        self.assertTrue(image_health.is_placeholder("http://localhost/img.jpg"))
        self.assertFalse(image_health.is_placeholder("https://cdn.mercadapp.services/a.png"))
        self.assertFalse(image_health.is_placeholder(None))

    def test_a_placeholder_is_dead_without_a_network_call(self):
        with patch.object(image_health.urllib.request, "urlopen", side_effect=AssertionError("must not call")):
            self.assertFalse(image_health.check("http://img.example/nescau.jpg"))
        self.assertTrue(image_health.is_dead("http://img.example/nescau.jpg", {}))

    def test_a_network_failure_is_unsure_not_dead(self):
        with patch.object(image_health.urllib.request, "urlopen", side_effect=TimeoutError("slow")):
            self.assertIsNone(image_health.check("https://cdn.loja.com.br/a.jpg"))


class PayloadImageTest(unittest.TestCase):
    class Member:
        def __init__(self, id):
            self.id = id

    def test_a_working_url_is_kept(self):
        health = {"https://cdn.loja.com.br/a.jpg": {"ok": True}}
        self.assertEqual(
            _public_image("https://cdn.loja.com.br/a.jpg", [self.Member(1)], {1: "images/aa/x.webp"}, health),
            "https://cdn.loja.com.br/a.jpg")

    def test_a_dead_url_becomes_the_mirrored_file(self):
        health = {"https://cdn.loja.com.br/a.jpg": {"ok": False}}
        self.assertEqual(
            _public_image("https://cdn.loja.com.br/a.jpg", [self.Member(1)], {1: "images/aa/x.webp"}, health),
            "/images/aa/x.webp")

    def test_a_dead_url_without_a_mirror_is_left_alone(self):
        health = {"https://cdn.loja.com.br/a.jpg": {"ok": False}}
        self.assertEqual(
            _public_image("https://cdn.loja.com.br/a.jpg", [self.Member(1)], {}, health),
            "https://cdn.loja.com.br/a.jpg")

    def test_a_missing_url_uses_the_mirror(self):
        self.assertEqual(
            _public_image(None, [self.Member(1)], {1: "images/aa/x.webp"}, {}),
            "/images/aa/x.webp")

    def test_an_unknown_url_is_not_second_guessed(self):
        self.assertEqual(
            _public_image("https://cdn.loja.com.br/new.jpg", [self.Member(1)], {1: "images/aa/x.webp"}, {}),
            "https://cdn.loja.com.br/new.jpg")

    def test_any_member_of_a_group_can_supply_the_mirror(self):
        health = {"https://cdn.loja.com.br/a.jpg": {"ok": False}}
        self.assertEqual(
            _public_image("https://cdn.loja.com.br/a.jpg", [self.Member(1), self.Member(2)], {2: "images/bb/y.webp"}, health),
            "/images/bb/y.webp")


class ManifestTest(unittest.TestCase):
    def test_the_publisher_lists_only_mirrored_images(self):
        from services.publish import _write_image_manifest, IMAGE_MANIFEST

        data = {"products": [
            {"image_url": "/images/aa/x.webp"},
            {"image_url": "/images/bb/y.webp"},
            {"image_url": "https://cdn.loja.com.br/a.jpg"},
            {"image_url": None},
        ]}
        original = IMAGE_MANIFEST.read_text(encoding="utf-8") if IMAGE_MANIFEST.exists() else None
        try:
            self.assertEqual(_write_image_manifest(data), 2)
            self.assertEqual(json.loads(IMAGE_MANIFEST.read_text(encoding="utf-8")),
                             ["images/aa/x.webp", "images/bb/y.webp"])
        finally:
            if original is None:
                IMAGE_MANIFEST.unlink(missing_ok=True)
            else:
                IMAGE_MANIFEST.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
