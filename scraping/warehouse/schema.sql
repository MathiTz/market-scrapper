-- Warehouse schema: the categorisation slice of the star schema.
--
-- Lives in its own file (scraping/warehouse.db) and never touches market.db. Price facts
-- (fact_price_observation / fact_current_offer) are added by the next ETL phase; the dimensions
-- and the classification cache they will point at are already here.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS etl_watermarks (
    pipeline_name         TEXT PRIMARY KEY,
    last_run_started_at   TEXT,
    last_run_completed_at TEXT,
    last_status           TEXT NOT NULL DEFAULT 'never_run',  -- running | ok | failed
    rows_processed        INTEGER NOT NULL DEFAULT 0,
    notes                 TEXT
);

-- One row per taxonomy node, including the synthetic out-of-taxonomy bucket.
CREATE TABLE IF NOT EXISTS dim_category (
    category_key      INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    path              TEXT NOT NULL,
    parent_slug       TEXT,
    level             INTEGER NOT NULL,
    is_leaf           INTEGER NOT NULL,
    source            TEXT NOT NULL DEFAULT 'cosmos',  -- cosmos | synthetic
    taxonomy_version  TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_dim_category_parent ON dim_category(parent_slug);
CREATE INDEX IF NOT EXISTS idx_dim_category_level  ON dim_category(level);

CREATE TABLE IF NOT EXISTS dim_brand (
    brand_key     INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_slug    TEXT NOT NULL UNIQUE,
    brand_name    TEXT NOT NULL,
    is_private_label INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Cleaned view of each product, keyed by the stable canonical key (a barcode or a hash of the
-- identity tokens + size). The market.db id is only a reference: it is local to one machine and
-- collides across rebuilds, so it can never be the identity here.
CREATE TABLE IF NOT EXISTS silver_products (
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
    category_source        TEXT,      -- cloud | rule | manual | outside | cache
    category_confidence    REAL,
    review_status          TEXT NOT NULL DEFAULT 'none',  -- none | pending
    updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_silver_products_cat  ON silver_products(category_slug);
CREATE INDEX IF NOT EXISTS idx_silver_products_src  ON silver_products(source_product_id);

-- Every model answer is cached, so a re-run never re-pays and every label has provenance.
CREATE TABLE IF NOT EXISTS silver_llm_cache (
    input_signature_hash TEXT NOT NULL,
    prompt_version       TEXT NOT NULL,
    method               TEXT NOT NULL,   -- cloud_leaf
    model                TEXT NOT NULL,
    answer_json          TEXT NOT NULL,
    confidence           REAL,
    latency_ms           INTEGER,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY (input_signature_hash, prompt_version, method)
);
CREATE INDEX IF NOT EXISTS idx_silver_cache_sig ON silver_llm_cache(input_signature_hash);

-- Classifications that failed a gate, for a human to settle.
CREATE TABLE IF NOT EXISTS silver_category_review (
    review_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_product_id  INTEGER NOT NULL,
    raw_name           TEXT NOT NULL,
    candidate_slug     TEXT,
    candidate_path     TEXT,
    confidence         REAL,
    reason             TEXT NOT NULL,  -- low_confidence | invalid_slug | no_answer
    status             TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    resolved_slug      TEXT,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    resolved_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_status ON silver_category_review(status);

-- ---------------------------------------------------------------------------
-- Snapshot ingestion (the online database is the trigger and the source)
-- ---------------------------------------------------------------------------

-- One row per published snapshot we consumed. The etag is the idempotency key: re-reading the same
-- snapshot is a no-op.
CREATE TABLE IF NOT EXISTS bronze_snapshots (
    snapshot_key    INTEGER PRIMARY KEY,   -- snapshots.id when read from Postgres; hash-derived for files
    etag            TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    product_count   INTEGER NOT NULL DEFAULT 0,
    offer_count     INTEGER NOT NULL DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'postgres',  -- postgres | file
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bronze_snapshots_etag ON bronze_snapshots(etag);

-- Append-only price observations, one row per offer per snapshot. This is what makes history
-- possible: every snapshot contributes a batch, and a repeat is ignored by the unique key.
CREATE TABLE IF NOT EXISTS fact_price_observation (
    observation_key        INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_key           INTEGER NOT NULL,
    product_key            TEXT NOT NULL,
    source_product_id      INTEGER,
    observed_at_iso        TEXT NOT NULL,
    store_name             TEXT NOT NULL,
    retailer_id            TEXT,
    price_cents            INTEGER NOT NULL,
    regular_price_cents    INTEGER,
    offer_label            TEXT,
    stock                  INTEGER,
    source_url             TEXT,
    UNIQUE (product_key, store_name, observed_at_iso, price_cents)
);
CREATE INDEX IF NOT EXISTS idx_fact_obs_product ON fact_price_observation(product_key, observed_at_iso);
CREATE INDEX IF NOT EXISTS idx_fact_obs_store   ON fact_price_observation(store_name, observed_at_iso);

-- Local image mirror, keyed by the stable product key rather than a market.db id.
CREATE TABLE IF NOT EXISTS warehouse_images (
    product_key   TEXT PRIMARY KEY,
    sha256        TEXT,
    path          TEXT,
    width         INTEGER,
    height        INTEGER,
    bytes         INTEGER,
    source_kind   TEXT,     -- snapshot | chain_search | openfoodfacts | web_search | manual
    source_url    TEXT,
    status        TEXT NOT NULL,   -- ok | review (operator-approved pending) | flagged
    decision      TEXT,
    checked_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_warehouse_images_status ON warehouse_images(status);
