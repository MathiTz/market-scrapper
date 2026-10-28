"""SQLite access for the warehouse."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from warehouse import config

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

# Columns added after a table was first created. ``create_all``-style DDL cannot add columns, so the
# warehouse gets the same explicit migration the operational database has.
_DROPPED = {"silver_products": ["d3_confirmed"]}

_MIGRATIONS = {
    "silver_products": {
        "image_url": "TEXT",
        "last_snapshot_key": "INTEGER",
        "last_seen_at": "TEXT",
    },
}


def _migrate(connection) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {row[1] for row in connection.execute(f"pragma table_info({table})")}
        for name, column_type in columns.items():
            if name not in existing:
                connection.execute(f"alter table {table} add column {name} {column_type}")
    _rekey_silver_products(connection)
    _drop_columns(connection)


def _drop_columns(connection) -> None:
    """Remove columns that later changes made meaningless (SQLite 3.35+)."""
    for table, columns in _DROPPED.items():
        existing = {row[1] for row in connection.execute(f"pragma table_info({table})")}
        for name in columns:
            if name in existing:
                connection.execute(f"alter table {table} drop column {name}")


def _rekey_silver_products(connection) -> None:
    """Rebuild silver_products with canonical_product_key as primary key.

    It used to be keyed by ``source_product_id`` (a market.db id). That is only unique inside one
    machine's database: ingesting a snapshot published elsewhere would overwrite unrelated rows.
    SQLite cannot change a primary key in place, so the table is copied and swapped once.
    """
    info = list(connection.execute("pragma table_info(silver_products)"))
    if not info:
        return
    primary = [row[1] for row in info if row[5]]
    if primary == ["canonical_product_key"]:
        return
    connection.executescript("""
        begin;
        alter table silver_products rename to silver_products_old;
        create table silver_products (
            canonical_product_key  TEXT PRIMARY KEY,
            source_product_id      INTEGER,
            raw_name               TEXT NOT NULL,
            display_name           TEXT NOT NULL,
            raw_brand              TEXT,
            gtin                   TEXT,
            identity_tokens_json   TEXT NOT NULL,
            amount                 INTEGER,
            unit                   TEXT,
            pack_count             INTEGER,
            total_base_amount      INTEGER,
            is_variable_weight     INTEGER NOT NULL DEFAULT 0,
            category_slug          TEXT,
            category_path          TEXT,
            category_source        TEXT,
            category_confidence    REAL,
            review_status          TEXT NOT NULL DEFAULT 'none',
            updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            image_url              TEXT,
            last_snapshot_key      INTEGER,
            last_seen_at           TEXT
        );
        insert or replace into silver_products
            (canonical_product_key, source_product_id, raw_name, display_name, raw_brand, gtin,
             identity_tokens_json, amount, unit, pack_count, total_base_amount, is_variable_weight,
             category_slug, category_path, category_source, category_confidence,
             review_status, updated_at, image_url, last_snapshot_key, last_seen_at)
        select canonical_product_key, source_product_id, raw_name, display_name, raw_brand, gtin,
             identity_tokens_json, amount, unit, pack_count, total_base_amount, is_variable_weight,
             category_slug, category_path, category_source, category_confidence,
             review_status, updated_at,
             image_url, last_snapshot_key, last_seen_at
        from silver_products_old order by updated_at;
        drop table silver_products_old;
        create index if not exists idx_silver_products_cat on silver_products(category_slug);
        create index if not exists idx_silver_products_src on silver_products(source_product_id);
        commit;
    """)


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path or config.WAREHOUSE_DB))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init(path: Optional[Path] = None) -> Path:
    """Create the file and every table (idempotent)."""
    target = Path(path or config.WAREHOUSE_DB)
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as connection:
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        _migrate(connection)
    return target


def source_market() -> sqlite3.Connection:
    """market.db opened READ-ONLY: the warehouse can never damage the operational data."""
    from config import BASE_DIR

    uri = f"file:{BASE_DIR / 'market.db'}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection
