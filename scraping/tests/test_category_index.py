"""Tests for the warehouse category index and the department shown as a chip."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services import category_index
from services.identity import canonical_key
from warehouse.ncm import department_for, read_heading_departments


def _database(folder: str, rows=(), with_table: bool = True) -> Path:
    path = Path(folder) / "warehouse.db"
    connection = sqlite3.connect(path)
    if with_table:
        connection.execute(
            "create table silver_products (canonical_product_key text, category_slug text, "
            "category_path text, ncm_code text)")
        connection.executemany("insert into silver_products values (?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()
    return path


class DepartmentTest(unittest.TestCase):
    def test_a_food_path_gives_its_department(self):
        self.assertEqual(
            category_index.department_of("Alimentos e Bebidas > Bebidas > Cervejas > Cervejas Tradicionais"),
            "Bebidas")

    def test_another_branch_is_its_own_department(self):
        # The other three branches have no comparable middle level, so the branch is the chip.
        self.assertEqual(category_index.department_of("Higiene e Beleza > Cuidados com o cabelo"),
                         "Higiene e Beleza")
        self.assertEqual(category_index.department_of("Limpeza > Limpadores Multi-uso"), "Limpeza")

    def test_an_empty_path_has_no_department(self):
        self.assertEqual(category_index.department_of(""), "")
        self.assertEqual(category_index.department_of(None), "")


class HeadingDepartmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = read_heading_departments()

    def test_the_headings_that_fill_the_cosmos_gaps_are_mapped(self):
        self.assertEqual(department_for("96190000", self.mapping), "Fraldas e Absorventes")
        self.assertEqual(department_for("48181000", self.mapping), "Papel Higiênico e Toalhas")
        self.assertEqual(department_for("23091000", self.mapping), "Pet")
        self.assertEqual(department_for("08031000", self.mapping), "Hortifruti")
        self.assertEqual(department_for("96039000", self.mapping), "Limpeza")

    def test_protein_concentrates_are_supplements_too(self):
        # 2106.10.00 is "concentrados de proteínas" - whey protein that the Cosmos tree has no node for.
        self.assertEqual(department_for("21061000", self.mapping), "Suplementos")

    def test_the_longest_key_wins(self):
        # 21069030 is "complementos alimentares"; the rest of heading 2106 is a catch-all and stays out.
        self.assertEqual(department_for("21069030", self.mapping), "Suplementos")
        self.assertIsNone(department_for("21069090", self.mapping))

    def test_an_unknown_or_missing_code_has_no_department(self):
        self.assertIsNone(department_for("94049000", self.mapping))
        self.assertIsNone(department_for(None, self.mapping))


class CategoryIndexTest(unittest.TestCase):
    def setUp(self):
        category_index._CACHE.update(stamp=None, index={})
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_a_missing_warehouse_publishes_without_categories(self):
        self.assertEqual(category_index.category_by_key(Path(self.folder.name) / "nope.db"), {})

    def test_a_database_without_the_table_is_not_an_error(self):
        path = _database(self.folder.name, with_table=False)
        self.assertEqual(category_index.category_by_key(path), {})

    def test_reads_the_leaf_and_its_department(self):
        key = "gtin:07891000053508"
        path = _database(self.folder.name, [
            (key, "cervejas", "Alimentos e Bebidas > Bebidas > Cervejas", "22030000"),
            ("tok:abc", "sabonetes-em-barra", "Higiene e Beleza > Sabonetes para o Corpo", "34013000"),
        ])
        self.assertEqual(category_index.category_by_key(path), {
            key: ("cervejas", "Bebidas"),
            "tok:abc": ("sabonetes-em-barra", "Higiene e Beleza"),
        })

    def test_a_product_outside_the_taxonomy_takes_its_department_from_the_ncm(self):
        # No Cosmos leaf, but a heading the curated table knows: nappies still reach a believable chip.
        path = _database(self.folder.name, [
            ("gtin:07891000053508", "fora-da-taxonomia", "Fora da taxonomia (não alimentício)", "96190000"),
        ])
        self.assertEqual(category_index.category_by_key(path),
                         {"gtin:07891000053508": (None, "Fraldas e Absorventes")})

    def test_an_outside_product_whose_heading_is_not_mapped_gets_nothing(self):
        # Heading 9404 is "cushions"; the model answered it for a nappy, and it is deliberately not guessed.
        path = _database(self.folder.name, [
            ("gtin:07891000053508", "fora-da-taxonomia", "Fora da taxonomia (não alimentício)", "94049000"),
        ])
        self.assertEqual(category_index.category_by_key(path), {})

    def test_a_refresh_is_seen_after_the_file_changes(self):
        path = _database(self.folder.name, [
            ("gtin:07891000053508", "cervejas", "Alimentos e Bebidas > Bebidas", "22030000")])
        category_index.category_by_key(path)
        connection = sqlite3.connect(path)
        connection.execute("insert into silver_products values ('tok:abc', 'arroz', "
                           "'Alimentos e Bebidas > Mercearia Alto Giro', '10063021')")
        connection.commit()
        connection.close()
        self.assertEqual(category_index.category_by_key(path)["tok:abc"], ("arroz", "Mercearia Alto Giro"))

    def test_category_for_uses_the_shared_identity(self):
        path = _database(self.folder.name, [
            ("gtin:07891000053508", "cervejas", "Alimentos e Bebidas > Bebidas", "22030000")])
        index = category_index.category_by_key(path)
        self.assertEqual(category_index.category_for({"name": "Cerveja 350ml", "gtin": "7891000053508"}, index),
                         ("cervejas", "Bebidas"))
        self.assertIsNone(category_index.category_for({"name": "Outra coisa", "gtin": None}, index))


if __name__ == "__main__":
    unittest.main()
