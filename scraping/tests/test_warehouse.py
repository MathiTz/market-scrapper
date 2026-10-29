"""Tests for the warehouse taxonomy, identity and classification - offline, no models."""

import json
import unittest
from unittest.mock import patch

from warehouse import config, etl
from warehouse.classifier import CloudClassifier
from warehouse.taxonomy import Taxonomy


class TaxonomyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = Taxonomy.load()

    def test_loads_every_node_from_the_csv(self):
        self.assertGreaterEqual(len(self.taxonomy.nodes), 278)
        self.assertGreaterEqual(len(self.taxonomy.leaves), 200)

    def test_has_the_eight_top_level_departments(self):
        names = {node.name for node in self.taxonomy.top_level}
        self.assertIn("Bebidas", names)
        self.assertIn("Matinais", names)
        self.assertEqual(len(self.taxonomy.top_level), 8)

    def test_slugs_are_unique(self):
        self.assertEqual(len(self.taxonomy.nodes), len(set(self.taxonomy.nodes)))

    def test_subtree_leaves_covers_a_department(self):
        bebidas = self.taxonomy.get("bebidas")
        leaves = self.taxonomy.subtree_leaves(bebidas.slug)
        self.assertTrue(leaves)
        self.assertTrue(all(leaf.is_leaf for leaf in leaves))
        self.assertTrue(all("Bebidas" in leaf.path for leaf in leaves))

    def test_unknown_slug_is_rejected(self):
        self.assertFalse(self.taxonomy.is_valid("nao-existe"))
        self.assertTrue(self.taxonomy.is_valid(config.OUTSIDE_SLUG))


class IdentityTest(unittest.TestCase):
    def test_gtin_is_zero_padded_to_fourteen(self):
        self.assertEqual(etl.normalize_gtin("7891000053508"), "07891000053508")

    def test_internal_plu_is_not_a_barcode(self):
        self.assertIsNone(etl.normalize_gtin("2000000000105"))

    def test_garbage_is_not_a_barcode(self):
        self.assertIsNone(etl.normalize_gtin("abc"))
        self.assertIsNone(etl.normalize_gtin("123"))

    def test_gtin_drives_the_canonical_key(self):
        product = {"name": "Cafe 500g", "gtin": "7891000053508"}
        self.assertEqual(etl.canonical_key(product), "gtin:07891000053508")

    def test_without_a_barcode_the_key_uses_tokens_and_size(self):
        a = etl.canonical_key({"name": "Café Solúvel 3 Corações 100g", "gtin": None})
        b = etl.canonical_key({"name": "CAFE SOLUVEL 3 CORACOES 100G", "gtin": None})
        self.assertTrue(a.startswith("tok:"))
        self.assertEqual(a, b)  # accent and case do not change identity

    def test_different_size_is_a_different_key(self):
        a = etl.canonical_key({"name": "Cafe Soluvel 3 Coracoes 100g", "gtin": None})
        b = etl.canonical_key({"name": "Cafe Soluvel 3 Coracoes 40g", "gtin": None})
        self.assertNotEqual(a, b)

    def test_signature_ignores_case_and_accents(self):
        from warehouse.classifier import signature

        self.assertEqual(signature("Café Solúvel", "3 Corações"), signature("cafe soluvél", "3 CORACOES"))


class CloudParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = Taxonomy.load()

    def _client(self):
        return CloudClassifier(self.taxonomy, api_key="test-key")

    def test_parses_a_valid_batch_answer(self):
        payload = {"message": {"content": json.dumps({"items": [
            {"i": 1, "slug": "arroz", "confidence": 0.93, "reason": "grains"},
        ]})}}
        products = [{"id": 10, "name": "Arroz Branco 5kg", "brand": "Camil"}]
        with patch("warehouse.classifier._post", return_value=payload):
            answers = self._client().classify_batch(products)
        self.assertEqual(answers[10]["slug"], "arroz")
        self.assertAlmostEqual(answers[10]["confidence"], 0.93)

    def test_drops_an_invented_slug(self):
        payload = {"message": {"content": json.dumps({"items": [
            {"i": 1, "slug": "cafe-inventado", "confidence": 0.99},
        ]})}}
        products = [{"id": 10, "name": "Cafe", "brand": None}]
        with patch("warehouse.classifier._post", return_value=payload):
            self.assertEqual(self._client().classify_batch(products), {})

    def test_survives_a_non_json_answer(self):
        payload = {"message": {"content": "desculpe, não sei"}}
        products = [{"id": 10, "name": "Cafe", "brand": None}]
        with patch("warehouse.classifier._post", return_value=payload):
            self.assertEqual(self._client().classify_batch(products), {})

    def test_without_a_key_it_does_nothing(self):
        products = [{"id": 10, "name": "Cafe", "brand": None}]
        self.assertFalse(CloudClassifier(self.taxonomy, api_key="").ready)
        self.assertEqual(CloudClassifier(self.taxonomy, api_key="").classify_batch(products), {})


class SnapshotTest(unittest.TestCase):
    def _payload(self, path):
        import json
        data = {"products": [], "offers": [], "generated_at": "2026-10-28T00:00:00+00:00"}
        open(path, "w").write(json.dumps(data))
        return path

    def test_read_file_returns_key_etag_and_data(self):
        import tempfile
        from warehouse import snapshot

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            path = self._payload(handle.name)
        payload = snapshot.read_file(path)
        self.assertEqual(payload["source"], "file")
        self.assertEqual(payload["data"]["products"], [])
        self.assertTrue(payload["etag"])

    def test_ingesting_the_same_snapshot_twice_is_a_no_op(self):
        import tempfile
        from unittest.mock import patch
        from warehouse import config as wh_config, snapshot

        with tempfile.TemporaryDirectory() as folder:
            database = f"{folder}/wh.db"
            payload_file = self._payload(f"{folder}/s.json")
            payload = snapshot.read_file(payload_file)
            with patch.object(wh_config, "WAREHOUSE_DB", __import__("pathlib").Path(database)):
                first = snapshot.ingest(payload, with_images=False)
                second = snapshot.ingest(payload, with_images=False)
        self.assertFalse(first["skipped"])
        self.assertTrue(second["skipped"])

    def test_product_key_prefers_the_barcode(self):
        from warehouse.etl import canonical_key

        self.assertEqual(canonical_key({"name": "Cafe 500g", "gtin": "7891000053508"}),
                         "gtin:07891000053508")
        self.assertTrue(canonical_key({"name": "Cafe 500g", "gtin": None}).startswith("tok:"))


if __name__ == "__main__":
    unittest.main()
