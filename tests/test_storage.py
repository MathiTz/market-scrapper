"""Tests for database storage operations."""

import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"  # never touch the real market.db

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from models.database import Base, _add_missing_columns
from models.product import Product
from models.store import Store
from models.price import Price


class TestSchemaUpgrade(unittest.TestCase):
    def test_adds_columns_missing_from_an_existing_table_and_keeps_rows(self):
        engine = create_engine("sqlite://")
        with engine.begin() as conn:  # a database created before regular_price/offer existed
            conn.execute(text("CREATE TABLE prices (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, "
                              "store_id INTEGER NOT NULL, price FLOAT NOT NULL, unit VARCHAR, url VARCHAR, "
                              "scraped_at DATETIME)"))
            conn.execute(text("INSERT INTO prices (product_id, store_id, price) VALUES (1, 1, 9.99)"))
        _add_missing_columns(engine)
        columns = {c["name"] for c in inspect(engine).get_columns("prices")}
        self.assertLessEqual({"regular_price", "offer"}, columns)
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT price, regular_price, offer FROM prices")).fetchall(),
                             [(9.99, None, None)])
        _add_missing_columns(engine)  # idempotent


class TestStorage(unittest.TestCase):
    def setUp(self):
        # Use an in-memory SQLite database for tests.
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_create_product(self):
        product = Product(name="Arroz 5kg")
        self.db.add(product)
        self.db.commit()
        self.assertIsNotNone(product.id)
        self.assertEqual(product.name, "Arroz 5kg")

    def test_create_store(self):
        store = Store(name="Pão de Açúcar", lat=-23.56, lon=-46.65)
        self.db.add(store)
        self.db.commit()
        self.assertIsNotNone(store.id)
        self.assertEqual(store.name, "Pão de Açúcar")

    def test_price_relationship(self):
        product = Product(name="Feijão 1kg")
        store = Store(name="Sams Club")
        self.db.add_all([product, store])
        self.db.commit()

        price = Price(product_id=product.id, store_id=store.id, price=7.50)
        self.db.add(price)
        self.db.commit()

        fetched = self.db.query(Price).first()
        self.assertEqual(fetched.price, 7.50)
        self.assertEqual(fetched.product_id, product.id)
        self.assertEqual(fetched.store_id, store.id)


if __name__ == "__main__":
    unittest.main()
