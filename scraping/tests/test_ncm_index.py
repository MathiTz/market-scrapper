"""Tests for the NCM index the publisher joins into the snapshot."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services import ncm_index
from services.identity import canonical_key


def _database(folder: str, rows=(), with_table: bool = True) -> Path:
    path = Path(folder) / "warehouse.db"
    connection = sqlite3.connect(path)
    if with_table:
        connection.execute("create table silver_products (canonical_product_key text, ncm_code text)")
        connection.executemany("insert into silver_products values (?, ?)", rows)
    connection.commit()
    connection.close()
    return path


class NcmIndexTest(unittest.TestCase):
    def setUp(self):
        # The module caches by (path, mtime, size); a fresh temp file per test keeps them apart.
        ncm_index._CACHE.update(stamp=None, index={})
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_a_missing_warehouse_publishes_without_codes(self):
        self.assertEqual(ncm_index.ncm_by_key(Path(self.folder.name) / "nope.db"), {})

    def test_a_database_without_the_table_is_not_an_error(self):
        path = _database(self.folder.name, with_table=False)
        self.assertEqual(ncm_index.ncm_by_key(path), {})

    def test_reads_the_keys_the_warehouse_writes(self):
        key = "gtin:07891000053508"
        path = _database(self.folder.name, [(key, "10063021"), ("tok:abc", None)])
        self.assertEqual(ncm_index.ncm_by_key(path), {key: "10063021"})  # null codes are skipped

    def test_a_refresh_is_seen_after_the_file_changes(self):
        path = _database(self.folder.name, [("gtin:07891000053508", "10063021")])
        ncm_index.ncm_by_key(path)
        connection = sqlite3.connect(path)
        connection.execute("insert into silver_products values ('tok:abc', '19059090')")
        connection.commit()
        connection.close()
        self.assertEqual(ncm_index.ncm_by_key(path)["tok:abc"], "19059090")

    def test_ncm_for_keys_a_product_the_way_the_warehouse_does(self):
        path = _database(self.folder.name, [("gtin:07891000053508", "10063021")])
        index = ncm_index.ncm_by_key(path)
        self.assertEqual(ncm_index.ncm_for({"name": "Arroz 5kg", "gtin": "7891000053508"}, index), "10063021")
        self.assertIsNone(ncm_index.ncm_for({"name": "Outra coisa", "gtin": None}, index))

    def test_the_key_is_the_shared_identity(self):
        # Whatever identity.py says is what the warehouse and the publisher must agree on.
        self.assertEqual(canonical_key({"name": "Café 500g", "gtin": "7891000053508"}), "gtin:07891000053508")


if __name__ == "__main__":
    unittest.main()
