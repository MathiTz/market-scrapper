"""Tests for the NCM layer: the official table, the leaf map, barcode answers and the ETL write."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from warehouse import config, db, etl, ncm
from warehouse.ncm import Code, Table


class CodeTest(unittest.TestCase):
    def test_dotted_codes_become_digits(self):
        self.assertEqual(ncm.normalize_code("1006.30.21"), "10063021")
        self.assertEqual(ncm.normalize_code("0101"), "0101")

    def test_partial_display_nodes_are_not_a_level(self):
        # BrasilAPI's "0101.2" (5 digits) is a display artefact, not a level of the classification.
        self.assertIsNone(ncm.normalize_code("0101.2"))
        self.assertIsNone(ncm.normalize_code("0101.21.0"))

    def test_garbage_is_rejected(self):
        self.assertIsNone(ncm.normalize_code(""))
        self.assertIsNone(ncm.normalize_code(None))
        self.assertIsNone(ncm.normalize_code("arroz"))


class TableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = Table.load()

    def test_carries_every_level_of_the_vendored_table(self):
        self.assertGreater(len(self.table), 10_000)
        levels = {c.level for c in self.table.codes.values()}
        self.assertEqual(levels, {2, 4, 6, 8})

    def test_a_known_item_and_its_description(self):
        arroz = self.table.get("10063021")
        self.assertIsNotNone(arroz)
        self.assertEqual(arroz.level, 8)
        self.assertEqual(arroz.chapter, "10")
        self.assertIn("Polido", arroz.description)

    def test_accents_survive_the_vendored_file(self):
        self.assertIn("raça", self.table.get("01012100").description)

    def test_the_table_has_a_version(self):
        self.assertTrue(self.table.version)

    def test_every_parent_is_a_real_code(self):
        # The chain can skip a level (0504.00 exists, 0504 does not), so the parent must be the
        # nearest ancestor that actually exists, never the code minus two digits.
        for code in self.table.codes.values():
            if code.level > 2:
                self.assertIn(code.parent, self.table.codes, code.code)

    def test_a_heading_with_no_subdivision_links_to_its_chapter(self):
        self.assertEqual(self.table.get("050400").parent, "05")
        self.assertEqual(self.table.get("05040011").parent, "050400")

    def test_unknown_codes_are_rejected_loudly(self):
        self.assertFalse(self.table.is_valid("99999999"))
        with self.assertRaises(ValueError):
            self.table.require("99999999", "test")


class CandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = Table.load()

    def test_beer_surfaces_for_the_beer_path(self):
        found = ncm.candidates(self.table, "Alimentos e Bebidas > Bebidas > Cervejas", limit=40)
        self.assertIn("22030000", [c.code for c in found])

    def test_no_shared_words_means_no_candidates(self):
        self.assertEqual(ncm.candidates(self.table, "zzzz qqqq"), [])


class CategoryMapTest(unittest.TestCase):
    def setUp(self):
        self.table = Table({"10063021": Code("10063021", 8, "10", "100630", "Arroz polido")})

    def _write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        return Path(handle.name)

    def test_reads_a_clean_map(self):
        path = self._write(
            "category_slug,category_path,category_name,ncm_code,ncm_description,confidence,source,reason\n"
            "arroz,Alimentos > Arroz,Arroz,10063021,Arroz polido,0.9,llm,test\n")
        mapping = ncm.read_category_map(path, self.table)
        self.assertEqual(mapping["arroz"].code, "10063021")
        self.assertEqual(mapping["arroz"].source, "llm")
        self.assertAlmostEqual(mapping["arroz"].confidence, 0.9)

    def test_a_typo_fails_the_load_instead_of_reaching_products(self):
        path = self._write(
            "category_slug,category_path,category_name,ncm_code,ncm_description,confidence,source,reason\n"
            "arroz,Alimentos > Arroz,Arroz,99999999,,0.9,llm,typo\n")
        with self.assertRaises(ValueError):
            ncm.read_category_map(path, self.table)

    def test_a_missing_file_is_an_empty_map(self):
        self.assertEqual(ncm.read_category_map(Path("/nonexistent/category-ncm.csv"), self.table), {})

    def test_the_committed_map_is_valid(self):
        mapping = ncm.read_category_map(table=Table.load())
        if len(mapping) < 100:
            self.skipTest("category-ncm.csv is still a partial draft")
        self.assertGreater(len(mapping), 100)
        for slug, entry in mapping.items():
            self.assertEqual(len(entry.code), 8, slug)


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.mapping = {"arroz": ncm.CategoryCode("arroz", "10063021", 0.9, "llm")}

    def test_the_barcode_answer_wins(self):
        answer = ncm.resolve("arroz", "07891000053508", self.mapping, {"07891000053508": "10063010"})
        self.assertEqual((answer.code, answer.source), ("10063010", "gtin"))

    def test_without_a_barcode_the_leaf_decides(self):
        answer = ncm.resolve("arroz", None, self.mapping, {})
        self.assertEqual((answer.code, answer.source), ("10063021", "leaf"))

    def test_nothing_known_means_no_answer(self):
        self.assertIsNone(ncm.resolve("nao-existe", "123", self.mapping, {}))
        self.assertIsNone(ncm.resolve(None, None, self.mapping, {}))


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = Path(self.folder.name) / "warehouse.db"
        self.addCleanup(self.folder.cleanup)
        with patch.object(config, "WAREHOUSE_DB", self.database):
            db.init()
            self.connection = db.connect()
            self.addCleanup(self.connection.close)

    def test_seed_mirrors_the_table_and_the_map(self):
        table = Table({"10063021": Code("10063021", 8, "10", "100630", "Arroz polido")}, version="v1")
        mapping = {"arroz": ncm.CategoryCode("arroz", "10063021", 0.9, "llm", "test")}
        ncm.seed(self.connection, table, mapping)
        self.assertEqual(self.connection.execute("select count(*) from dim_ncm").fetchone()[0], 1)
        row = self.connection.execute("select * from map_category_ncm").fetchone()
        self.assertEqual((row["category_slug"], row["ncm_code"]), ("arroz", "10063021"))

    def test_barcode_answers_round_trip_and_are_padded(self):
        written = ncm.import_answers(self.connection, [("7891000053508", "10063021")])
        self.assertEqual(written, 1)
        self.assertEqual(ncm.answers(self.connection), {"07891000053508": "10063021"})

    def test_a_short_barcode_is_not_stored(self):
        self.assertEqual(ncm.import_answers(self.connection, [("123", "10063021")]), 0)


class EtlWriteTest(unittest.TestCase):
    """The ETL writes the code the maps say, with its provenance."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "warehouse.db"
        with patch.object(config, "WAREHOUSE_DB", self.database):
            db.init()
            self.connection = db.connect()
            self.addCleanup(self.connection.close)
            self.connection.execute(
                """insert into silver_products
                     (canonical_product_key, raw_name, display_name, identity_tokens_json,
                      category_slug, gtin)
                   values ('gtin:07891000053508', 'Arroz 5kg', 'Arroz 5kg', '[]', 'arroz',
                           '07891000053508')""")
            self.connection.execute(
                """insert into map_category_ncm (category_slug, ncm_code, confidence, source)
                   values ('arroz', '10063021', 0.9, 'llm')""")
            self.connection.commit()

    def _apply(self):
        mapping = {"arroz": ncm.CategoryCode("arroz", "10063021", 0.9, "llm")}
        with patch.object(config, "WAREHOUSE_DB", self.database), \
                patch.object(etl.ncm, "read_category_map", return_value=mapping):
            etl.apply_ncm()

    def test_apply_ncm_fills_the_products_already_classified(self):
        self._apply()
        row = self.connection.execute(
            "select ncm_code, ncm_source, ncm_confidence from silver_products").fetchone()
        self.assertEqual((row["ncm_code"], row["ncm_source"]), ("10063021", "leaf"))
        self.assertAlmostEqual(row["ncm_confidence"], 0.9)

    def test_apply_ncm_does_not_erase_a_product_level_code(self):
        self.connection.execute(
            """update silver_products set ncm_code='23091000', ncm_source='product', ncm_confidence=0.9""")
        self.connection.commit()
        with patch.object(config, "WAREHOUSE_DB", self.database), \
                patch.object(etl.ncm, "read_category_map", return_value={}):
            etl.apply_ncm()
        row = self.connection.execute("select ncm_code, ncm_source from silver_products").fetchone()
        self.assertEqual((row["ncm_code"], row["ncm_source"]), ("23091000", "product"))

    def test_a_barcode_answer_overrides_the_leaf(self):
        self.connection.execute(
            """insert into map_gtin_ncm (gtin, ncm_code, source, confidence)
               values ('07891000053508', '10063010', 'cosmos', 1.0)""")
        self.connection.commit()
        self._apply()
        row = self.connection.execute("select ncm_code, ncm_source from silver_products").fetchone()
        self.assertEqual((row["ncm_code"], row["ncm_source"]), ("10063010", "gtin"))


class ImportTest(unittest.TestCase):
    def test_import_rejects_a_code_outside_the_table(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        csv.writer(handle).writerows([["gtin", "ncm"], ["7891000053508", "99999999"],
                                      ["7891000053508", "10063021"]])
        handle.close()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.object(config, "WAREHOUSE_DB", Path(folder.name) / "w.db"):
            etl.import_gtin_csv(handle.name)
            with patch.object(config, "WAREHOUSE_DB", Path(folder.name) / "w.db"):
                connection = db.connect()
                try:
                    rows = connection.execute("select gtin, ncm_code from map_gtin_ncm").fetchall()
                finally:
                    connection.close()
        self.assertEqual([(r["gtin"], r["ncm_code"]) for r in rows], [("07891000053508", "10063021")])


if __name__ == "__main__":
    unittest.main()
