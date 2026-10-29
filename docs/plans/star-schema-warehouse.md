# IMPLEMENTATION PLAN: Market-Scrapper Analytical Data Warehouse & LLM Taxonomy Engine

---

## (1) Summary

This document specifies the design and rollout of a dedicated analytical data warehouse (`scraping/warehouse.db`) and a swappable, cost-bounded LLM classification pipeline for **Mercado em Dia** (`market-scrapper`).

- **Zero Modification to Operational Pipeline**: `scraping/market.db`, SQLAlchemy operational models (`scraping/models/*`), `refresh.py`, and `services/publish.py` remain completely untouched. The warehouse is populated out-of-band via a new standalone CLI (`scraping/warehouse_etl.py`) that attaches to `market.db` in read-only mode (`?mode=ro`).
- **Medallion Architecture in a Single SQLite File**: `scraping/warehouse.db` hosts Bronze (incremental raw ingestion logs & watermarks), Silver (cleaned, size-parsed, brand-normalized, entity-resolved records, plus persistent LLM classification cache and human review queue), and Gold (Kimball star schema with surrogate keys, hierarchy-aware category dimension, and current + historical price fact tables).
- **Resilient Canonical Identity**: Because `market.db` `products.id` is an unstable auto-increment integer assigned per chain-specific product name, the warehouse introduces a deterministic `canonical_product_key` (`gtin:<ean>` when valid, or `tok:<sha256_16>` derived from sorted `match_tokens(name)` + normalized `(amount, unit, pack_count)`). It survives complete deletions and rebuilds of `market.db`.
- **Auditable, Swappable LLM Categorization**: Products are classified into a 3-level Brazilian grocery taxonomy (12 L1 departments, 42 L2 categories, ~110 L3 subcategories) using batched, JSON-schema-constrained calls to either a local Ollama endpoint or a cheap hosted API (e.g., Gemini 2.5 Flash-Lite / GPT-4o-mini). Classifications are cached by `input_signature_hash` so unchanged products never re-trigger LLM calls, low-confidence predictions (`< 0.70`) route to a manual review queue while falling back to the existing deterministic `categorize()`/`subcategorize()` rules, and parallel work (such as image enrichment) runs without lock contention or schema conflicts.

---

## (2) Current-State Findings Verified by Reading

Inspection of `/home/iviless/myCode/mercado/market-scrapper` confirmed the following exact mechanics and edge cases that the warehouse must account for:

1. **Chain-Specific Product Rows (`scraping/services/scraper_service.py`)**:
   - `_get_or_create_product()` matches strictly on `Product.name.ilike(entry.product_name)`. Because each supermarket chain formats names differently (e.g., `"LASANHA SADIA BOLONHESA 600G"` vs. `"Lasanha Bolonhesa Sadia Pacote 600g"`), the same physical SKU exists as multiple rows in `products`.
   - `brand`, `gtin`, and `image_url` are populated via backfill-only logic (lines 85–90: filled once if null, never overwritten by a source that omits them). Currently, only VTEX-backed scrapers (`AtacadaoScraper`, `PaoDeAcucarScraper`, `SamsClubScraper`, etc.) supply GTIN/brand/image for free; others leave them `NULL`.
   - `Product.category` and `Product.unit` columns exist in `scraping/models/product.py` (lines 13–14) but are never populated by `scraper_service.py`.

2. **In-Place Price Overwrites & Binary Ring Buffer (`scraping/services/scraper_service.py`, `scraping/models/price_history.py`)**:
   - `prices` holds **only one row per `(product_id, store_id)`**, updated in-place by `_upsert_price()` (lines 94–122).
   - When `round(existing.price * 100) != round(entry.price * 100)`, the old `(price, scraped_at)` is packed into an 8-byte big-endian binary struct (`_ENTRY = struct.Struct(">II")` -> `(uint32 price_cents, uint32 unix_epoch_utc)`) and appended to `price_history.blob`, capped at `HISTORY_CAP = 20` entries (160 bytes max).
   - If a scrape reconfirms the exact same price, `prices.scraped_at` and `prices.run_id` are updated in-place without writing to `price_history`. Consequently, `market.db` loses historical price observations beyond 20 price *changes* unless the warehouse captures each run incrementally.

3. **Duplicate Store Rows & Active-Run Filtering (`scraping/services/public_api.py`, `scraping/services/store_locations.py`)**:
   - `stores` contains duplicate rows per chain name from multiple seed executions. `build_public()` (lines 460–464) and `_store_branches()` (line 64) canonicalize a chain to `MIN(stores.id)` per `stores.name`.
   - `Store.address/lat/lon/city/state/cep` are legacy placeholders ignored by the API. Real physical branches live in `store_locations(id, store_id, external_id, name, address, lat, lon, updated_at)` with unique constraint `(store_id, external_id)`. Note: the model columns in `scraping/models/store_location.py` are `lat` and `lon` (mapped to `latitude`/`longitude` in JSON).
   - Not every row in `prices` is an active offer: `_listed_runs()` (lines 338–360) inspects `scrape_attempts` for each `site_key` (mapped via `ALL_SCRAPERS` in `scraper/sites/__init__.py`: `atacadao`, `carnauba`, `centerbox`, `cometa`, `mercadinho`, `pao_de_acucar`, `pinheiro`, `sams_club`) and selects the newest successful `run_id` where `items_found >= 0.25 * max(previous_6_successful_runs)`. Prices with an older `run_id` are delisted/stale.

4. **Build-Time Entity Resolution & Derived Attributes (`scraping/services/public_api.py`)**:
   - `parse_size(name)` (lines 102–117) extracts `(amount, unit, pack_count)` where `unit` is normalized to `'g'`, `'ml'`, or `'un'` (`kg -> 1000g`, `l -> 1000ml`, bare `kg`/`quilo` -> `(1000, 'g', pack)` for variable-weight meat/produce).
   - `match_tokens(name)` (lines 397–401) strips sizes (`_SIZE_RE`), packs (`_PACK_RE`), percentages, accents (`clean()`), and 37 packaging/promo stop-words (`_NOT_IDENTITY`), returning a `frozenset` of alphanumeric tokens.
   - `match_products(products)` (lines 404–440) buckets products with `len(tokens) >= 2`, sub-groups by `(amount, unit, pack_count)`, attaches unsized `(1, 'un', pack)` flyer items only when a bucket has a single unambiguous size for that `pack`, and elects `min(m.id)` as the group representative.
   - Club deals (`_CLUB_RE = r"(\w*clube\w*)"`, e.g., `"PinClube"`, `"Clube Tem Mais"`) split a single `prices` row into two public offers when `regular_price` is present: one standard offer at `regular_price` and one club-conditioned offer at `price`.
   - Categorization (`categorize()` / `subcategorize()`, lines 59–204) uses 9 hardcoded keyword tuples (`_CATEGORIES`) plus `"Outros"`. It strips `r"\bsabor\s+\w+"`, checks multi-word prefixes, then the first 3 words, then anywhere in the string. Subcategories are simply the matched keyword title-cased (excluding generic words in `_NOT_SUBCATEGORY`). Products without keyword matches fall into `"Outros"` (~10% of catalog) with an empty `""` subcategory.

5. **Cloud Publishing Contract (`scraping/services/publish.py`, `api/src/store.ts`, `web/INTEGRACAO.md`)**:
   - `publish.py` serializes `build_public(db)` into a single JSON text blob in Postgres `snapshots(id, generated_at, etag, payload)` and prunes all but the latest 5 rows. The Hono API (`api/src/store.ts`) serves `payload` raw without parsing.

---

## (3) Proposed Architecture

### 3.1 File & Directory Layout

All new code lives under `scraping/warehouse/` with a single CLI entry point at `scraping/warehouse_etl.py` and tests under `scraping/tests/test_warehouse.py`:

```text
scraping/
├── warehouse_etl.py                 # Standalone CLI entry point (never called by refresh.py)
├── warehouse/
│   ├── __init__.py
│   ├── config.py                    # Warehouse env vars (WAREHOUSE_DB_PATH, LLM_*, thresholds)
│   ├── db.py                        # SQLite/Postgres connection factory, DDL runner, ATTACH helper
│   ├── schema.sql                   # Complete idempotent DDL for Bronze, Silver, and Gold tables
│   ├── taxonomy.py                  # 3-level Brazilian grocery taxonomy definitions & seed loader
│   ├── normalizer.py                # Brand normalization, canonical_product_key, token/size wrappers
│   ├── matcher.py                   # Cross-chain entity resolution (GTIN + token/size grouping)
│   ├── classifier.py                # Swappable LLM Classifier protocol, Ollama/OpenAI/Gemini adapters, FakeClassifier
│   ├── etl.py                       # Incremental Bronze -> Silver -> Gold pipeline orchestrator
│   └── exporter.py                  # Analytical views & optional review-queue CLI helpers
└── tests/
    └── test_warehouse.py            # Offline unit + integration tests (in-memory SQLite + FakeClassifier)
```

### 3.2 Medallion Layering inside `scraping/warehouse.db`

```
+-----------------------------------------------------------------------------------+
|                        SOURCE: scraping/market.db (READ-ONLY)                     |
|    products | stores | store_locations | prices | price_history | scrape_attempts |
+-----------------------------------------------------------------------------------+
                                          |
                     ATTACH DATABASE 'market.db?mode=ro' AS src
                                          v
+-----------------------------------------------------------------------------------+
|                        WAREHOUSE: scraping/warehouse.db                           |
|                                                                                   |
|  [BRONZE LAYER: Incremental Capture & Watermarks]                                 |
|   - etl_watermarks          (tracks last ingested scrape_attempt_id, timestamps)  |
|   - bronze_scrape_attempts  (immutable copy of scrape_attempts)                   |
|   - bronze_products_raw     (source_product_id, raw name/brand/gtin/image, hash)  |
|   - bronze_prices_log       (append-only log of every price change + unpacked     |
|                              price_history ring-buffer entries)                   |
|                                          |                                        |
|                                          v                                        |
|  [SILVER LAYER: Cleaned, Normalized, Resolved & Classified]                       |
|   - silver_brand_aliases    (raw brand/token -> canonical brand name)             |
|   - silver_products         (1 row per source_product_id: cleaned name, parsed    |
|                              amount/unit/pack, canonical_brand, assigned          |
|                              canonical_product_key, match_method, input_sig_hash) |
|   - silver_llm_cache        (keyed by input_sig_hash -> LLM JSON, confidence,     |
|                              model, prompt_version; prevents re-paying on reruns) |
|   - silver_category_review  (manual review queue for confidence < 0.70 or         |
|                              rule/LLM conflicts; supports human overrides)        |
|                                          |                                        |
|                                          v                                        |
|  [GOLD LAYER: Kimball Star Schema]                                                |
|   Dimensions:                                                                     |
|   - dim_date                (date_key YYYYMMDD, day_of_week, month, holiday_br)   |
|   - dim_category            (category_key, L1/L2/L3 hierarchy, slug, rule_equiv)  |
|   - dim_brand               (brand_key, canonical_brand, is_private_label, owner) |
|   - dim_store               (store_key, canonical_source_store_id, chain_name,    |
|                              site_key, website)                                   |
|   - dim_location            (location_key, store_key, external_id, branch_name,   |
|                              city, neighborhood, lat, lon)                        |
|   - dim_product             (product_key, canonical_product_key, display_name,    |
|                              brand_key, primary_category_key, amount, unit,       |
|                              pack_count, gtin, image_url, classification_source)  |
|   Bridges:                                                                        |
|   - bridge_product_source   (product_key <-> source_product_id, store_key,        |
|                              match_method, match_confidence)                      |
|   - bridge_product_category (product_key <-> category_key, role: primary/secondary)|
|   Facts:                                                                          |
|   - fact_price_observation  (grain: 1 row per canonical product x store x         |
|                              scrape_run / price timestamp; regular_cents,         |
|                              effective_cents, club_cents, unit_price_cents, ...)  |
|   - fact_current_offer      (grain: 1 row per active offer variant on the         |
|                              store's current listed run, ready for BI/UI)         |
|   - fact_daily_category_Summary (optional pre-aggregated daily category index)    |
+-----------------------------------------------------------------------------------+
```

### 3.3 Canonical Product Identity Strategy (`canonical_product_key`)

#### Why `market.db` IDs Fail as Warehouse Keys
1. `products.id` is an SQLite auto-increment integer assigned in arrival order. If `market.db` is deleted and re-scraped, `"Arroz Tio João 1kg"` gets a completely different `products.id`.
2. Different chains produce distinct `products` rows for the exact same physical item.
3. In `public_api.py::match_products()`, the group ID is `min(m.id for m in members)`. If a newly scraped chain happens to have a lower or higher ID after a DB rebuild, every group ID shifts.

#### Proposed Deterministic Key Construction
Every source product row is mapped to a stable string identifier `canonical_product_key` using a two-tier hierarchy in `warehouse/matcher.py`:

1. **Tier 1 — Verified GTIN (`gtin:<normalized_gtin14>`)**:
   - If the product row has a valid EAN/GTIN passing `valid_ean()` (8, 12, 13, or 14 digits, non-zero), normalize it to a 14-digit zero-padded string (so `"7891000100103"` and `"07891000100103"` collide identically) and emit `gtin:07891000100103`.
   - **Cross-Chain Bridging via Shared Tokens**: If Product A (from Pão de Açúcar, VTEX) has `gtin = "7891000100103"` and `(tokens, size) = ({'leite', 'condensado', 'moca'}, (395, 'g', 1))`, and Product B (from Centerbox, non-VTEX, `gtin = NULL`) has the exact same `(tokens, size)` bucket, Product B inherits `gtin:07891000100103` during the batch matching phase (`match_method = 'token_bridged_to_gtin'`).

2. **Tier 2 — Deterministic Identity Hash (`tok:<sha256_prefix_16>`)**:
   - When no member of a matched `(tokens, size)` group has a valid GTIN:
     - Extract `tokens = sorted(match_tokens(name))` (using the exact same `_NOT_IDENTITY` and cleaning rules as `public_api.py`).
     - Extract `(amount, unit, pack_count) = parse_size(name)` (after resolving unsized `(1, 'un', pack)` flyer items against single-size buckets, identical to `match_products()` lines 424–436).
     - If `len(tokens) >= 2`, compute:
       `signature = f"{'|'.join(tokens)}::{amount}:{unit}:{pack_count}"`
       `canonical_product_key = "tok:" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]`
   - **Fallback for 1-token generic names (`len(tokens) < 2`, e.g., `"Arroz"`)**:
     - Do not merge across chains (prevents false matches). Compute `signature = f"single::{clean(name)}::{amount}:{unit}:{pack_count}"` and prefix with `"raw:" + sha256[:16]`.

#### Consequences & Trade-Offs of This Key Design
- **Survives `market.db` Rebuild**: Rebuilding `market.db` from scratch produces the exact same `gtin:...` and `tok:...` keys, preserving all historical facts in `warehouse.db` and all cached LLM classifications in `silver_llm_cache`.
- **Late-Arriving GTIN Promotion (Key Evolution)**: Suppose Product X is first scraped only from Pinheiro (no GTIN), receiving `canonical_product_key = 'tok:9f86d081884c7d65'`. Two weeks later, Pão de Açúcar lists the same item with `gtin = '7891000100103'`.
  - *Handling in ETL*: `matcher.py` detects that the token bucket `tok:9f86d081884c7d65` now resolves to `gtin:07891000100103`. Instead of creating a second `dim_product` row and orphaning old facts, the ETL updates `dim_product.canonical_product_key` in-place on the existing `product_key` surrogate integer (and records the old `tok:...` key in `dim_product.previous_canonical_key` for auditability). Because fact tables reference the integer surrogate `product_key`, **zero fact rows need to be rewritten**.
- **False-Positive vs. False-Negative Risk**:
  - Some chains reuse a generic barcode for variable-weight produce/butcher items (e.g., internal PLU codes starting with `2` of length 13, such as `2000000001234`). **Rule**: Any 13-digit code starting with `"2"` (GS1 variable-measure restricted distribution prefix) is rejected as a global GTIN in `normalizer.py::normalize_gtin()` and forced into Tier 2 (`tok:...`) so two chains' internal butcher PLUs never falsely collide.

---

## (4) Full DDL (`scraping/warehouse/schema.sql`)

The DDL below is valid SQLite 3.35+ (using `STRICT`-compatible affinities, `GENERATED` or standard columns, and `ON CONFLICT` upserts). Differences for PostgreSQL are noted at the end of Section 4.

```sql
-- =============================================================================
-- scraping/warehouse/schema.sql
-- Target: SQLite 3 (scraping/warehouse.db)
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- 1. BRONZE LAYER (Raw Incremental Capture & ETL State)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS etl_watermarks (
    pipeline_name           TEXT PRIMARY KEY,
    last_scrape_attempt_id  INTEGER NOT NULL DEFAULT 0,
    last_run_started_at     TEXT,
    last_run_completed_at   TEXT,
    last_status             TEXT NOT NULL DEFAULT 'never_run', -- 'running' | 'ok' | 'failed'
    rows_processed          INTEGER NOT NULL DEFAULT 0,
    notes                   TEXT
);

CREATE TABLE IF NOT EXISTS bronze_scrape_attempts (
    attempt_id              INTEGER PRIMARY KEY, -- exact scrape_attempts.id from market.db
    site_key                TEXT NOT NULL,
    query                   TEXT,
    success                 INTEGER NOT NULL,    -- 0 or 1
    error                   TEXT,
    items_found             INTEGER NOT NULL,
    duration_ms             REAL,
    run_id                  TEXT,
    created_at              TEXT NOT NULL,
    ingested_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_bronze_attempts_site_run
    ON bronze_scrape_attempts(site_key, run_id);

CREATE TABLE IF NOT EXISTS bronze_products_raw (
    source_product_id       INTEGER PRIMARY KEY, -- market.db products.id
    raw_name                TEXT NOT NULL,
    raw_brand               TEXT,
    raw_category            TEXT,
    raw_unit                TEXT,
    raw_gtin                TEXT,
    raw_image_url           TEXT,
    source_created_at       TEXT,
    row_hash                TEXT NOT NULL,       -- sha256 of (raw_name, raw_brand, raw_gtin, raw_image_url)
    first_seen_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Append-only log of every distinct price observation captured from market.db `prices`
-- and unpacked from `price_history.blob`.
CREATE TABLE IF NOT EXISTS bronze_prices_log (
    bronze_price_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_product_id       INTEGER NOT NULL,
    source_store_id         INTEGER NOT NULL,
    observed_at_epoch       INTEGER NOT NULL,    -- UTC unix seconds (matches PriceHistory struct)
    observed_at_iso         TEXT NOT NULL,       -- UTC ISO-8601
    price_cents             INTEGER NOT NULL,
    regular_price_cents     INTEGER,
    offer_label             TEXT,
    stock                   INTEGER,
    url                     TEXT,
    run_id                  TEXT,
    record_origin           TEXT NOT NULL,       -- 'prices_current' | 'price_history_blob'
    ingested_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (source_product_id, source_store_id, observed_at_epoch, price_cents)
);
CREATE INDEX IF NOT EXISTS idx_bronze_prices_lookup
    ON bronze_prices_log(source_product_id, source_store_id, observed_at_epoch DESC);
CREATE INDEX IF NOT EXISTS idx_bronze_prices_run
    ON bronze_prices_log(run_id);

-- -----------------------------------------------------------------------------
-- 2. SILVER LAYER (Cleaned, Normalized, Entity-Resolved & LLM Cache)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS silver_brand_aliases (
    alias_clean             TEXT PRIMARY KEY,    -- clean(raw_brand) e.g. 'nestle brasil', 'sadia s.a.'
    canonical_brand         TEXT NOT NULL,       -- e.g. 'Nestlé', 'Sadia'
    parent_company          TEXT,                -- e.g. 'Nestlé', 'BRF'
    is_private_label        INTEGER NOT NULL DEFAULT 0,
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS silver_products (
    source_product_id       INTEGER PRIMARY KEY, -- 1:1 with bronze_products_raw.source_product_id
    raw_name                TEXT NOT NULL,
    clean_name              TEXT NOT NULL,       -- public_api.clean(raw_name)
    display_name            TEXT NOT NULL,       -- public_api.display_name(raw_name)
    identity_tokens_json    TEXT NOT NULL,       -- sorted JSON array of match_tokens(raw_name)
    amount                  INTEGER NOT NULL,    -- parsed amount in base unit (g, ml, un)
    unit                    TEXT NOT NULL CHECK (unit IN ('g', 'ml', 'un')),
    pack_count              INTEGER NOT NULL DEFAULT 1,
    is_variable_weight      INTEGER NOT NULL DEFAULT 0, -- 1 when matched _BARE_KG_RE
    normalized_gtin         TEXT,                -- 14-digit zero-padded EAN (NULL if invalid or internal PLU 2xxxx)
    raw_brand               TEXT,
    canonical_brand         TEXT,                -- resolved via silver_brand_aliases or token extraction
    image_url               TEXT,
    rule_category           TEXT NOT NULL,       -- fallback from public_api.categorize()
    rule_subcategory        TEXT NOT NULL,       -- fallback from public_api.subcategorize()
    canonical_product_key   TEXT NOT NULL,       -- 'gtin:...' | 'tok:...' | 'raw:...'
    match_method            TEXT NOT NULL,       -- 'gtin_exact' | 'token_bridged_to_gtin' | 'token_size' | 'unsized_inferred' | 'singleton'
    input_signature_hash    TEXT NOT NULL,       -- sha256(clean_name || '::' || coalesce(canonical_brand,'') || '::' || amount || unit)
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_silver_products_canonical
    ON silver_products(canonical_product_key);
CREATE INDEX IF NOT EXISTS idx_silver_products_sig
    ON silver_products(input_signature_hash);

-- Persistent cache of LLM categorizations so re-runs and DB rebuilds never re-pay.
CREATE TABLE IF NOT EXISTS silver_llm_cache (
    input_signature_hash    TEXT NOT NULL,
    prompt_version          TEXT NOT NULL,       -- e.g. 'v1.0'
    canonical_product_key   TEXT NOT NULL,
    sample_name             TEXT NOT NULL,
    sample_brand            TEXT,
    provider                TEXT NOT NULL,       -- 'ollama' | 'gemini' | 'openai_compat' | 'fake'
    model_name              TEXT NOT NULL,       -- e.g. 'qwen2.5:7b-instruct', 'gemini-2.5-flash-lite'
    l1_slug                 TEXT NOT NULL,
    l2_slug                 TEXT NOT NULL,
    l3_slug                 TEXT NOT NULL,
    extracted_brand         TEXT,
    extracted_variant       TEXT,
    confidence              REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    reasoning_short         TEXT,
    raw_response_json       TEXT NOT NULL,
    latency_ms              INTEGER,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (input_signature_hash, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_silver_llm_cache_cpk
    ON silver_llm_cache(canonical_product_key);

-- Human-in-the-loop review queue for low-confidence (< 0.70) or conflicting classifications.
CREATE TABLE IF NOT EXISTS silver_category_review (
    review_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_product_key   TEXT NOT NULL UNIQUE,
    sample_name             TEXT NOT NULL,
    sample_brand            TEXT,
    rule_category           TEXT NOT NULL,
    rule_subcategory        TEXT NOT NULL,
    llm_l1_slug             TEXT,
    llm_l2_slug             TEXT,
    llm_l3_slug             TEXT,
    llm_confidence          REAL,
    reason_code             TEXT NOT NULL,       -- 'low_confidence' | 'invalid_taxonomy_slug' | 'rule_disagreement_high' | 'unclassified'
    status                  TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved_llm', 'approved_override', 'ignored')),
    override_l1_slug        TEXT,
    override_l2_slug        TEXT,
    override_l3_slug        TEXT,
    override_brand          TEXT,
    reviewer_note           TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_silver_review_status
    ON silver_category_review(status);

-- -----------------------------------------------------------------------------
-- 3. GOLD LAYER (Kimball Star Schema: Dimensions, Bridges, Facts)
-- -----------------------------------------------------------------------------

-- 3.1 Dimension: Date (dim_date)
CREATE TABLE IF NOT EXISTS dim_date (
    date_key                INTEGER PRIMARY KEY, -- YYYYMMDD e.g. 20261028
    full_date               TEXT NOT NULL UNIQUE,-- '2026-10-28'
    year                    INTEGER NOT NULL,
    quarter                 INTEGER NOT NULL,
    month                   INTEGER NOT NULL,
    month_name_pt           TEXT NOT NULL,       -- 'Outubro'
    day_of_month            INTEGER NOT NULL,
    day_of_week             INTEGER NOT NULL,    -- 0=Mon .. 6=Sun (ISO)
    day_name_pt             TEXT NOT NULL,       -- 'Quarta-feira'
    is_weekend              INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
    is_fortaleza_holiday    INTEGER NOT NULL DEFAULT 0,
    is_fifth_business_day   INTEGER NOT NULL DEFAULT 0 -- Brazilian payday spike indicator
);

-- 3.2 Dimension: Category Hierarchy (dim_category) - 3 Levels Max
CREATE TABLE IF NOT EXISTS dim_category (
    category_key            INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_slug           TEXT NOT NULL UNIQUE,-- e.g. 'laticinios-e-frios/leites-e-derivados/creme-de-leite'
    l1_slug                 TEXT NOT NULL,       -- 'laticinios-e-frios'
    l1_name                 TEXT NOT NULL,       -- 'Laticínios e Frios'
    l2_slug                 TEXT NOT NULL,       -- 'leites-e-derivados'
    l2_name                 TEXT NOT NULL,       -- 'Leites e Derivados'
    l3_slug                 TEXT NOT NULL,       -- 'creme-de-leite'
    l3_name                 TEXT NOT NULL,       -- 'Creme de Leite'
    legacy_category_name    TEXT NOT NULL,       -- Maps back to existing UI's 10 categories (e.g. 'Laticínios e frios')
    legacy_subcategory_name TEXT NOT NULL,       -- Maps back to existing UI's product.subcategory
    is_food                 INTEGER NOT NULL DEFAULT 1,
    is_perishable           INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_dim_category_l1_l2
    ON dim_category(l1_slug, l2_slug);

-- 3.3 Dimension: Brand (dim_brand)
-- Surrogate key 1 is reserved for 'Sem Marca / Desconhecida'
CREATE TABLE IF NOT EXISTS dim_brand (
    brand_key               INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_slug              TEXT NOT NULL UNIQUE,-- clean(canonical_brand) e.g. 'nestle'
    brand_name              TEXT NOT NULL,       -- display form e.g. 'Nestlé'
    parent_company          TEXT,
    is_private_label        INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- 3.4 Dimension: Store / Retailer Chain (dim_store)
-- Deduplicates market.db `stores` (where seed ran multiple times) to 1 row per chain.
CREATE TABLE IF NOT EXISTS dim_store (
    store_key               INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_name              TEXT NOT NULL UNIQUE,-- e.g. 'Pinheiro', 'Pão de Açúcar', 'São Luiz'
    site_key                TEXT NOT NULL UNIQUE,-- e.g. 'pinheiro', 'pao_de_acucar', 'mercadinho'
    canonical_source_id     INTEGER NOT NULL,    -- MIN(stores.id) in market.db
    website                 TEXT,
    supports_gtin           INTEGER NOT NULL DEFAULT 0,
    supports_club_price     INTEGER NOT NULL DEFAULT 0,
    active_run_id           TEXT,                -- latest complete run_id per _listed_runs() rule
    last_scrape_status      TEXT,                -- 'ok' | 'failed' | 'empty' | 'set_aside'
    last_scrape_error       TEXT,
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- 3.5 Dimension: Physical Store Location (dim_location)
CREATE TABLE IF NOT EXISTS dim_location (
    location_key            INTEGER PRIMARY KEY AUTOINCREMENT,
    store_key               INTEGER NOT NULL REFERENCES dim_store(store_key),
    external_id             TEXT NOT NULL,       -- store_locations.external_id
    source_location_id      INTEGER,             -- store_locations.id in market.db
    branch_name             TEXT NOT NULL,
    address                 TEXT NOT NULL,
    city                    TEXT NOT NULL DEFAULT 'Fortaleza',
    state                   TEXT NOT NULL DEFAULT 'CE',
    latitude                REAL NOT NULL,
    longitude               REAL NOT NULL,
    is_active               INTEGER NOT NULL DEFAULT 1,
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (store_key, external_id)
);

-- 3.6 Dimension: Canonical Product (dim_product)
CREATE TABLE IF NOT EXISTS dim_product (
    product_key                 INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_product_key       TEXT NOT NULL UNIQUE, -- 'gtin:0789...' or 'tok:a1b2...'
    previous_canonical_key      TEXT,                 -- populated if promoted from tok:... to gtin:...
    display_name                TEXT NOT NULL,        -- best-reading name across matched chain rows
    clean_search_text           TEXT NOT NULL,        -- accent-free concatenation for search
    brand_key                   INTEGER NOT NULL REFERENCES dim_brand(brand_key),
    primary_category_key        INTEGER NOT NULL REFERENCES dim_category(category_key),
    variant                     TEXT NOT NULL DEFAULT '', -- e.g. 'Zero Lactose', 'Bolonhesa'
    amount                      INTEGER NOT NULL,     -- base unit quantity (e.g. 600)
    unit                        TEXT NOT NULL CHECK (unit IN ('g', 'ml', 'un')),
    pack_count                  INTEGER NOT NULL DEFAULT 1,
    total_base_amount           INTEGER NOT NULL,     -- amount * pack_count (for R$/kg or R$/L math)
    is_variable_weight          INTEGER NOT NULL DEFAULT 0,
    gtin                        TEXT,                 -- 8/12/13/14-digit display barcode
    image_url                   TEXT,
    classification_source       TEXT NOT NULL CHECK (classification_source IN ('manual_override', 'llm_high_conf', 'rule_fallback')),
    classification_confidence   REAL NOT NULL DEFAULT 0.0,
    first_seen_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_dim_product_category ON dim_product(primary_category_key);
CREATE INDEX IF NOT EXISTS idx_dim_product_brand ON dim_product(brand_key);
CREATE INDEX IF NOT EXISTS idx_dim_product_gtin ON dim_product(gtin) WHERE gtin IS NOT NULL;

-- 3.7 Bridge: Canonical Product <-> Source Chain Product Rows (bridge_product_source)
-- Resolves the M:1 relationship between market.db `products.id` (chain-specific) and `dim_product`.
CREATE TABLE IF NOT EXISTS bridge_product_source (
    source_product_id       INTEGER PRIMARY KEY, -- market.db products.id
    product_key             INTEGER NOT NULL REFERENCES dim_product(product_key),
    primary_store_key       INTEGER REFERENCES dim_store(store_key),
    source_raw_name         TEXT NOT NULL,
    match_method            TEXT NOT NULL,       -- 'gtin_exact' | 'token_bridged_to_gtin' | 'token_size' | 'unsized_inferred' | 'singleton'
    match_confidence        REAL NOT NULL DEFAULT 1.0,
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_bridge_product_source_pk
    ON bridge_product_source(product_key);

-- 3.8 Bridge: Product <-> Category Many-to-Many (bridge_product_category)
-- Allows a product to have 1 primary category and optional secondary/cross-merchandising categories
-- (e.g. 'Leite Sem Lactose' in both 'Laticínios/Leites' and 'Saudáveis e Dietéticos/Zero Lactose').
CREATE TABLE IF NOT EXISTS bridge_product_category (
    product_key             INTEGER NOT NULL REFERENCES dim_product(product_key),
    category_key            INTEGER NOT NULL REFERENCES dim_category(category_key),
    category_role           TEXT NOT NULL CHECK (category_role IN ('primary', 'secondary')),
    allocation_weight       REAL NOT NULL DEFAULT 1.0, -- 1.0 for primary, 0.0 for secondary so SUM() facts don't double-count
    assigned_by             TEXT NOT NULL,             -- 'llm' | 'rule' | 'manual'
    PRIMARY KEY (product_key, category_key)
);
CREATE INDEX IF NOT EXISTS idx_bridge_prod_cat_cat
    ON bridge_product_category(category_key, category_role);

-- 3.9 Fact Table 1: Historical Price Observations (fact_price_observation)
-- Grain: One row per (source_product_id, store_key, observed_at_epoch).
-- Captures every price point over time (both unpacked price_history blobs and ongoing scrapes).
CREATE TABLE IF NOT EXISTS fact_price_observation (
    observation_key         INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key                INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key             INTEGER NOT NULL REFERENCES dim_product(product_key),
    source_product_id       INTEGER NOT NULL,
    store_key               INTEGER NOT NULL REFERENCES dim_store(store_key),
    category_key            INTEGER NOT NULL REFERENCES dim_category(category_key), -- snapshot of primary category
    brand_key               INTEGER NOT NULL REFERENCES dim_brand(brand_key),
    observed_at_epoch       INTEGER NOT NULL,
    observed_at_iso         TEXT NOT NULL,
    run_id                  TEXT,
    is_complete_run         INTEGER NOT NULL DEFAULT 1, -- 1 if run passed _listed_run() 25% threshold
    price_cents             INTEGER NOT NULL,           -- scraped price in cents
    regular_price_cents     INTEGER,                    -- undiscounted price when promo/club
    effective_ordinary_cents INTEGER NOT NULL,          -- price paid by non-club shopper
    effective_club_cents    INTEGER,                    -- price paid by club member (NULL if not club deal)
    discount_pct            REAL,                       -- (regular - price) / regular * 100
    price_per_kg_or_l_cents INTEGER,                    -- normalized price per 1000g or 1000ml (NULL if unit='un')
    price_per_unit_cents    INTEGER NOT NULL,           -- price_cents / pack_count
    is_promotion            INTEGER NOT NULL DEFAULT 0,
    is_club_only            INTEGER NOT NULL DEFAULT 0,
    club_name               TEXT,
    offer_label             TEXT,
    stock                   INTEGER,
    record_origin           TEXT NOT NULL,              -- 'prices_current' | 'price_history_blob'
    UNIQUE (source_product_id, store_key, observed_at_epoch)
);
CREATE INDEX IF NOT EXISTS idx_fact_obs_prod_date
    ON fact_price_observation(product_key, date_key);
CREATE INDEX IF NOT EXISTS idx_fact_obs_store_date
    ON fact_price_observation(store_key, date_key);
CREATE INDEX IF NOT EXISTS idx_fact_obs_cat_date
    ON fact_price_observation(category_key, date_key);

-- 3.10 Fact Table 2: Current Listed Offers (fact_current_offer)
-- Grain: One row per (product_key, store_key, price_tier) currently live on the store's active run.
-- Rebuilt atomically on each ETL run; powers instant cross-chain price comparisons and BI dashboards.
CREATE TABLE IF NOT EXISTS fact_current_offer (
    offer_key               TEXT PRIMARY KEY,           -- '<product_key>-<store_key>' or '<product_key>-<store_key>-club'
    date_key                INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key             INTEGER NOT NULL REFERENCES dim_product(product_key),
    store_key               INTEGER NOT NULL REFERENCES dim_store(store_key),
    category_key            INTEGER NOT NULL REFERENCES dim_category(category_key),
    brand_key               INTEGER NOT NULL REFERENCES dim_brand(brand_key),
    source_product_id       INTEGER NOT NULL,
    price_tier              TEXT NOT NULL CHECK (price_tier IN ('ordinary', 'club')),
    price_cents             INTEGER NOT NULL,
    regular_price_cents     INTEGER,
    price_per_kg_or_l_cents INTEGER,
    price_per_unit_cents    INTEGER NOT NULL,
    is_cheapest_for_product INTEGER NOT NULL DEFAULT 0, -- 1 if lowest ordinary price across all chains for this product_key
    chain_count_for_product INTEGER NOT NULL DEFAULT 1, -- how many chains currently sell this product_key
    spread_pct_vs_cheapest  REAL NOT NULL DEFAULT 0.0,  -- (price_cents - min_price_cents) / min_price_cents * 100
    club_name               TEXT,
    deal_label              TEXT,
    stock                   INTEGER,
    source_url              TEXT,
    observed_at_iso         TEXT NOT NULL,
    run_id                  TEXT
);
CREATE INDEX IF NOT EXISTS idx_fact_curr_prod ON fact_current_offer(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_curr_cat ON fact_current_offer(category_key);
CREATE INDEX IF NOT EXISTS idx_fact_curr_store ON fact_current_offer(store_key);
```

### 4.1 What Changes If Deployed to PostgreSQL (Neon) Instead of SQLite

Because `warehouse/db.py` isolates dialect specifics, migrating the warehouse to Postgres requires only:
1. **Auto-increment syntax**: Replace `INTEGER PRIMARY KEY AUTOINCREMENT` with `BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY`.
2. **Timestamps & Booleans**: Replace `TEXT` ISO timestamps with `TIMESTAMPTZ DEFAULT now()`, and `INTEGER` flags (`0`/`1`) with `BOOLEAN` (or keep `SMALLINT` for zero-query-change parity).
3. **Cross-database ingestion**: SQLite uses `ATTACH DATABASE '/path/to/market.db?mode=ro' AS src` to move rows in set-based SQL. For a remote Postgres warehouse, `warehouse/etl.py` reads `market.db` via a local read-only SQLite connection and streams batches into Postgres using `psycopg` `cursor.executemany()` or `COPY ... FROM STDIN` with `ON CONFLICT DO UPDATE`.

---

## (5) Brazilian Grocery Taxonomy & LLM Categorization Design

### 5.1 Proposed 3-Level Brazilian Grocery Taxonomy (`scraping/warehouse/taxonomy.py`)

The taxonomy has **at most 3 levels** (`L1 Department -> L2 Category -> L3 Subcategory`), with an explicit `legacy_category_name` mapping on every node so the existing 10 UI categories (`Mercearia`, `Limpeza`, `Higiene e beleza`, `Bebidas`, `Carnes e peixes`, `Laticínios e frios`, `Hortifruti`, `Padaria e biscoitos`, `Outros`) remain 100% backward-compatible.

| L1 Department (`l1_name` / `l1_slug`) | L2 Category (`l2_name` / `l2_slug`) | Representative L3 Subcategories (`l3_name` / `l3_slug`) | Maps to Legacy UI Category |
| :--- | :--- | :--- | :--- |
| **1. Mercearia Salgada** (`mercearia-salgada`) | Grãos e Cereais (`graos-e-cereais`) | Arroz Branco/Parboilizado (`arroz`), Feijão Carioca/Preto (`feijao`), Milho de Pipoca (`pipoca`), Lentilha e Grão-de-Bico (`leguminosas`) | `Mercearia` |
| | Massas e Molhos (`massas-e-molhos`) | Macarrão Seco (`macarrao`), Macarrão Instantâneo (`lamen-miojo`), Massa para Lasanha (`massa-lasanha`), Molho e Extrato de Tomate (`molho-tomate`) | `Mercearia` |
| | Óleos, Azeites e Temperos (`oleos-e-temperos`) | Óleo Vegetal (`oleo-vegetal`), Azeite de Oliva (`azeite`), Vinagre (`vinagre`), Sal (`sal`), Maionese/Ketchup/Mostarda (`condimentos`), Caldos e Temperos (`temperos`) | `Mercearia` |
| | Farináceos e Enlatados (`farinaceos-e-enlatados`) | Farinha de Trigo (`farinha-trigo`), Farinha de Mandioca/Tapioca (`tapioca-mandioca`), Flocão e Milho (`flocao-cuscuz`), Atum e Sardinha (`peixe-enlatado`), Milho/Ervilha/Palmito (`conservas-vegetais`) | `Mercearia` |
| **2. Mercearia Doce e Matinais** (`mercearia-doce`) | Café, Chá e Achocolatados (`cafe-e-matinais`) | Café Torrado e Moído (`cafe-moido`), Café Solúvel e Cápsulas (`cafe-soluvel-capsula`), Achocolatado em Pó (`achocolatado`), Chá e Mate (`cha`), Aveia, Granola e Cereal (`cereais-matinais`) | `Mercearia` |
| | Açúcar, Doces e Confeitaria (`acucar-e-confeitaria`) | Açúcar e Adoçante (`acucar-adocante`), Leite Condensado (`leite-condensado`), Creme de Leite UHT/Lata (`creme-de-leite-mercearia`), Gelatina e Sobremesas (`gelatina-sobremesa`), Mel, Geleia e Doce de Leite (`geleia-doce-leite`), Fermento e Misturas (`mistura-bolo`) | `Mercearia` |
| | Chocolates, Balas e Snacks (`chocolates-e-snacks`) | Chocolate em Barra e Bombom (`chocolate-bombom`), Salgadinho e Batata Chips (`salgadinho-chips`), Amendoim e Castanhas (`castanhas-amendoim`), Balas e Chicletes (`balas-chicletes`) | `Mercearia` |
| **3. Padaria e Biscoitos** (`padaria-e-biscoitos`) | Biscoitos e Bolachas (`biscoitos-e-bolachas`) | Biscoito Recheado e Wafer (`biscoito-recheado`), Biscoito Cream Cracker e Água e Sal (`biscoito-salgado`), Biscoito Maisena e Maria (`biscoito-doce`), Cookies (`cookie`), Torradas (`torrada`) | `Padaria e biscoitos` |
| | Pães e Bolos (`paes-e-bolos`) | Pão de Forma (`pao-de-forma`), Bisnaguinha e Pão de Leite (`bisnaguinha`), Pão Francês e Artesanal (`pao-fresco`), Bolo Pronto e Panetone (`bolo-pronto`), Rap10 e Tortilhas (`tortilha-wrap`) | `Padaria e biscoitos` |
| **4. Laticínios e Frios** (`laticinios-e-frios`) | Leites e Bebidas Lácteas (`leites-e-lacteos`) | Leite UHT Integral/Desnatado (`leite-uht`), Leite em Pó e Composto Lácteo (`leite-em-po`), Leite Vegetal (`leite-vegetal`), Bebida Láctea (`bebida-lactea`) | `Laticínios e frios` |
| | Queijos e Requeijão (`queijos`) | Queijo Mussarela e Prato (`mussarela-prato`), Queijo Coalho e Minas (`coalho-minas`), Queijo Ralado e Parmesão (`queijo-ralado`), Requeijão e Cream Cheese (`requeijao`), Ricota e Cottage (`ricota-cottage`) | `Laticínios e frios` |
| | Iogurtes, Manteigas e Ovos (`iogurtes-manteiga-ovos`) | Iogurte e Leite Fermentado (`iogurte`), Manteiga (`manteiga`), Margarina (`margarina`), Creme de Leite Fresco/Nata (`nata-creme-fresco`), Ovos (`ovos`) | `Laticínios e frios` |
| | Frios e Embutidos Fatiados (`frios-fatiados`) | Presunto e Apresuntado (`presunto`), Peito de Peru e Blanquet (`peito-de-peru`), Mortadela e Salame (`mortadela-salame`) | `Laticínios e frios` |
| **5. Carnes, Aves e Peixes** (`carnes-aves-peixes`) | Bovinos (`bovinos`) | Cortes Nobres — Picanha/Maminha/Alcatra (`bovino-nobre`), Cortes do Dia — Acém/Patinho/Músculo (`bovino-dia-a-dia`), Carne Moída e Costela (`bovino-moida-costela`), Carne de Sol e Charque (`carne-de-sol-charque`) | `Carnes e peixes` |
| | Aves (`aves`) | Peito e Filé de Frango (`frango-peito`), Coxa e Sobrecoxa (`frango-coxa-sobrecoxa`), Frango Inteiro e Passarinho (`frango-inteiro`), Peru e Aves Natalinas (`aves-especiais`) | `Carnes e peixes` |
| | Suínos e Linguiças (`suinos-e-linguicas`) | Bisteca, Lombo e Pernil Suíno (`cortes-suinos`), Linguiça Toscana e Calabresa (`linguica`), Bacon (`bacon`), Salsicha (`salsicha`) | `Carnes e peixes` |
| | Peixes e Frutos do Mar (`peixes-e-mariscos`) | Tilápia e Merluza (`peixe-branco`), Salmão (`salmao`), Bacalhau (`bacalhau`), Camarão e Mariscos (`camarao-mariscos`) | `Carnes e peixes` |
| **6. Congelados e Pratos Prontos** (`congelados`) | Pratos Prontos e Empanados (`pratos-prontos`) | Lasanha e Massas Congeladas (`lasanha-congelada`), Pizza Congelada (`pizza-congelada`), Hambúrguer e Almôndega (`hamburguer`), Empanados e Nuggets (`empanados`), Pão de Queijo e Batata Congelada (`pao-queijo-batata-cong`) | `Carnes e peixes` (for meat items) or `Mercearia` |
| | Sorvetes e Açaí (`sorvetes-e-acai`) | Sorvete de Massa e Picolé (`sorvete`), Açaí e Polpa de Fruta (`acai-polpa`) | `Laticínios e frios` |
| **7. Hortifruti** (`hortifruti`) | Frutas (`frutas`) | Banana, Maçã e Pera (`frutas-dia-a-dia`), Laranja, Limão e Tangerina (`citricos`), Melancia, Melão e Mamão (`frutas-grandes`), Uva, Morango e Kiwi (`frutas-delicadas`), Abacate, Manga e Abacaxi (`frutas-tropicais`) | `Hortifruti` |
| | Legumes, Verduras e Temperos (`legumes-e-verduras`) | Batata, Cebola e Alho (`batata-cebola-alho`), Tomate, Cenoura e Beterraba (`legumes`), Alface, Couve, Brócolis e Repolho (`folhosos-verduras`), Cheiro-Verde e Pimentão (`temperos-frescos`) | `Hortifruti` |
| **8. Bebidas** (`bebidas`) | Não Alcoólicas (`nao-alcoolicas`) | Refrigerante (`refrigerante`), Água Mineral e de Coco (`agua`), Suco e Néctar (`suco-nectar`), Energético e Isotônico (`energetico-isotonico`) | `Bebidas` |
| | Alcoólicas (`alcoolicas`) | Cerveja (`cerveja`), Vinho e Espumante (`vinho-espumante`), Destilados — Whisky/Vodka/Gin/Cachaça (`destilados`), Ice e Bebidas Mistas (`bebida-mista`) | `Bebidas` |
| **9. Limpeza** (`limpeza`) | Roupas (`limpeza-roupas`) | Lava-Roupas Líquido e Pó (`sabao-roupas`), Amaciante (`amaciante`), Tira-Manchas e Alvejante (`alvejante-tira-manchas`) | `Limpeza` |
| | Cozinha, Banheiro e Casa (`limpeza-casa`) | Detergente Lava-Louças (`detergente`), Água Sanitária e Desinfetante (`desinfetante-agua-sanitaria`), Multiuso e Limpadores (`limpador-multiuso`), Esponja, Pano e Saco de Lixo (`acessorios-limpeza`), Inseticida e Odorizador (`inseticida-odorizador`) | `Limpeza` |
| **10. Higiene e Beleza** (`higiene-e-beleza`) | Cabelo e Corpo (`cabelo-e-corpo`) | Shampoo e Condicionador (`shampoo-condicionador`), Creme de Tratamento e Coloração (`tratamento-capilar`), Sabonete Barra e Líquido (`sabonete`), Desodorante (`desodorante`), Hidratante e Protetor Solar (`hidratante-solar`) | `Higiene e beleza` |
| | Higiene Bucal e Pessoal (`bucal-e-pessoal`) | Creme Dental (`creme-dental`), Escova, Fio Dental e Enxaguante (`escova-enxaguante`), Papel Higiênico e Lenço (`papel-higienico`), Absorvente e Higiene Íntima (`absorvente`), Barba e Algodão/Hastes (`barba-algodao`) | `Higiene e beleza` |
| **11. Bebê e Infantil** (`bebe-e-infantil`) | Fraldas e Cuidados (`fraldas-e-higiene-bebe`) | Fralda Descartável (`fralda`), Lenço Umedecido e Pomada (`lenco-umedecido`), Fórmula Infantil e Papinha (`nutricao-infantil`) | `Higiene e beleza` |
| **12. Pet, Bazar e Utilidades** (`pet-e-bazar`) | Pet Shop (`pet-shop`) | Ração e Petisco para Cães/Gatos (`racao-pet`), Higiene Pet (`higiene-pet`) | `Outros` |
| | Descartáveis e Utilidades (`descartaveis-e-bazar`) | Papel Toalha, Guardanapo e Alumínio (`papel-toalha-guardanapo`), Copos, Pratos e Embalagens (`descartaveis`), Carvão e Churrasco (`carvao-churrasco`), Lâmpadas, Pilhas e Utilidades (`utilidades-domesticas`) | `Outros` |

### 5.2 How LLM Classification Interacts with `categorize()` / `subcategorize()`

The warehouse resolves a product's final category using a strict priority waterfall in `warehouse/etl.py`:

1. **Priority 1 — Approved Human Override (`silver_category_review.status = 'approved_override'`)**:
   - Uses `override_l1_slug / override_l2_slug / override_l3_slug`. Sets `dim_product.classification_source = 'manual_override'` and `classification_confidence = 1.0`.
2. **Priority 2 — Cached High-Confidence LLM Classification (`confidence >= 0.70` and valid taxonomy slug)**:
   - Uses the LLM's `l1_slug / l2_slug / l3_slug` (looked up against `dim_category`). Sets `classification_source = 'llm_high_conf'`.
   - **Conflict Audit**: If `rule_category != 'Outros'` and the LLM's mapped `legacy_category_name` disagrees with `rule_category` (e.g., rule says `"Carnes e peixes"` because the string contained `"Picanha"`, while LLM says `"Mercearia"` because the product is `"Sal Grosso para Churrasco Picanha"`):
     - If `llm_confidence >= 0.85`, the LLM wins (fixing keyword false-positives like `"Sal para Picanha"` or `"Ração Sabor Frango"`), and an informational row is written to `silver_category_review` with `reason_code = 'rule_disagreement_high'`.
     - If `0.70 <= llm_confidence < 0.85`, the item is queued in `silver_category_review` (`status = 'pending'`) and falls back to Priority 3 until reviewed.
3. **Priority 3 — Deterministic Rule Fallback (`categorize()` + `subcategorize()`)**:
   - Used whenever the LLM is disabled (`--no-llm`), unreachable, returns an invalid slug not in `dim_category`, or returns `confidence < 0.70`.
   - Every `(categorize(name), subcategorize(name))` pair has a deterministic mapping in `warehouse/taxonomy.py::RULE_TO_TAXONOMY_SLUG` (e.g., `("Limpeza", "Agua Sanitaria") -> "limpeza/limpeza-casa/desinfetante-agua-sanitaria"`).
   - Sets `classification_source = 'rule_fallback'`. If `llm_confidence < 0.70` or `rule_category == 'Outros'`, inserts/updates a `pending` row in `silver_category_review`.

### 5.3 Swappable Classifier Architecture (`scraping/warehouse/classifier.py`)

No extra heavy SDK is required (`requests` is already in `scraping/requirements.txt`).

```python
@dataclass(frozen=True)
class ProductClassificationInput:
    input_signature_hash: str
    canonical_product_key: str
    clean_name: str
    display_name: str
    raw_brand: Optional[str]
    amount: int
    unit: str
    pack_count: int
    rule_category: str
    rule_subcategory: str

@dataclass(frozen=True)
class ProductClassificationResult:
    input_signature_hash: str
    l1_slug: str
    l2_slug: str
    l3_slug: str
    extracted_brand: Optional[str]
    extracted_variant: Optional[str]
    confidence: float
    reasoning_short: str
    raw_json: str

class ClassifierProvider(Protocol):
    provider_name: str
    model_name: str
    def classify_batch(
        self, items: Sequence[ProductClassificationInput]
    ) -> Dict[str, ProductClassificationResult]: ...
```

Supported providers selected via `WAREHOUSE_LLM_PROVIDER` env var or `--llm-provider` CLI flag:
- `ollama`: POSTs to `http://localhost:11434/api/chat` (recommended local models: `qwen2.5:7b-instruct` or `llama3.1:8b`) with `"format": <JSON_SCHEMA>` and `"options": {"temperature": 0.0, "seed": 42}`.
- `openai_compat`: POSTs to `${WAREHOUSE_LLM_BASE_URL}/v1/chat/completions` with `response_format={"type": "json_schema", ...}` and `temperature=0.0` (works with Gemini OpenAI-compatible endpoint, OpenRouter, Groq, vLLM, or OpenAI `gpt-4o-mini`).
- `gemini`: POSTs to `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent` with `generationConfig={"temperature": 0.0, "responseMimeType": "application/json", "responseSchema": ...}`.
- `none` / `fake`: Skips network calls (`none` uses rule fallback only; `fake` is used in unit tests).

### 5.4 Batching, Caching & Determinism Mechanics

1. **Deduplication Before Calling LLM**:
   - Multiple chain rows sharing the same `canonical_product_key` (or identical `input_signature_hash = sha256(f"{clean_name}::{canonical_brand or ''}::{amount}{unit}")`) are collapsed to **1 classification item**.
   - Before making any HTTP request, `etl.py` queries `silver_llm_cache` for `(input_signature_hash, PROMPT_VERSION)`. Only cache misses are sent.
2. **Batch Size**:
   - **25 products per HTTP request** (`WAREHOUSE_LLM_BATCH_SIZE = 25`), sorted deterministically by `input_signature_hash` so batch composition is repeatable.
   - At 25 items per batch, classifying an entire initial catalog of 2,500 canonical products takes only **100 requests** (~$0.03 total on `gemini-2.5-flash-lite` or free on local Ollama), and subsequent daily runs only classify the ~5–30 newly discovered products (1–2 requests/day).
3. **Strict Validation**:
   - Each returned item is validated in Python: `(l1_slug, l2_slug, l3_slug)` must exist in `taxonomy.VALID_SLUGS`, and `0.0 <= confidence <= 1.0`. If an item fails schema validation or is omitted by the model, it is logged and routed to `silver_category_review` with `reason_code = 'invalid_taxonomy_slug'`, falling back to `rule_category`.

### 5.5 Sample Prompt and Response Schema

**Prompt Version**: `PROMPT_VERSION = "v1.0"`

**System Prompt**:
```text
Você é um especialista em catalogação de supermercados brasileiros (Fortaleza, CE).
Sua tarefa é classificar cada produto da lista em EXATAMENTE UM caminho da taxonomia (l1_slug, l2_slug, l3_slug) fornecida abaixo, extrair a marca limpa (extracted_brand) se identificável no nome, e extrair a variante/sabor (extracted_variant).

REGRAS DE CLASSIFICAÇÃO:
1. O TIPO DO PRODUTO decide a categoria, NUNCA o sabor ou o uso culinário:
   - "Lámen Nissin Sabor Picanha 85g" -> mercearia-salgada / massas-e-molhos / lamen-miojo (NÃO é bovinos).
   - "Sal Grosso para Churrasco Picanha 1kg" -> mercearia-salgada / oleos-e-temperos / sal.
   - "Ração Pedigree Carne e Frango 1kg" -> pet-e-bazar / pet-shop / racao-pet.
   - "Água Sanitária Ypê 2L" -> limpeza / limpeza-casa / desinfetante-agua-sanitaria (NÃO é agua).
2. Escolha APENAS slugs que existam exatamente na lista TAXONOMIA PERMITIDA.
3. "confidence" deve ser um número entre 0.0 e 1.0 refletindo a certeza da classificação. Se o nome for vago ou truncado (ex: "Oferta Especial 500g"), use confidence < 0.50.
4. Responda EXCLUSIVAMENTE com um objeto JSON seguindo o schema especificado.

TAXONOMIA PERMITIDA (l1_slug / l2_slug / l3_slug):
- mercearia-salgada/graos-e-cereais/arroz
- mercearia-salgada/graos-e-cereais/feijao
- mercearia-salgada/massas-e-molhos/macarrao
- mercearia-salgada/massas-e-molhos/lamen-miojo
- mercearia-salgada/massas-e-molhos/molho-tomate
[... full list of ~110 valid slug triples injected from taxonomy.py ...]
```

**User Prompt (Batch of 25 items)**:
```json
{
  "products": [
    {
      "sig": "8a4f2c91e0b311d4",
      "name": "Macarrão Instantâneo Nissin Lámen Carne 85g",
      "brand_hint": "Nissin",
      "size": "85g x 1",
      "rule_hint": "Mercearia / Lamen"
    },
    {
      "sig": "3b9104e27c11a89f",
      "name": "Ração Úmida Whiskas Sachê Frango ao Molho 85g",
      "brand_hint": null,
      "size": "85g x 1",
      "rule_hint": "Carnes e peixes / Frango"
    }
  ]
}
```

**Structured Output JSON Schema & Sample Response**:
```json
{
  "classifications": [
    {
      "sig": "8a4f2c91e0b311d4",
      "l1_slug": "mercearia-salgada",
      "l2_slug": "massas-e-molhos",
      "l3_slug": "lamen-miojo",
      "extracted_brand": "Nissin",
      "extracted_variant": "Carne",
      "confidence": 0.98,
      "reasoning_short": "Macarrão instantâneo tipo lámen sabor carne."
    },
    {
      "sig": "3b9104e27c11a89f",
      "l1_slug": "pet-e-bazar",
      "l2_slug": "pet-shop",
      "l3_slug": "racao-pet",
      "extracted_brand": "Whiskas",
      "extracted_variant": "Frango ao Molho",
      "confidence": 0.99,
      "reasoning_short": "Alimento úmido para gatos (Whiskas), apesar da palavra frango."
    }
  ]
}
```

---

## (6) ETL Flow Step-by-Step (`scraping/warehouse_etl.py` & `scraping/warehouse/etl.py`)

### 6.1 Coexistence with `refresh.py` and Parallel Image Enrichment
- **Completely Decoupled Execution**: `refresh.py` continues to scrape chains into `market.db` and publish the JSON snapshot to Neon Postgres without knowing `warehouse.db` exists.
- **Read-Only Source Access**: `warehouse_etl.py` opens `market.db` using `sqlite3.connect("file:/.../market.db?mode=ro", uri=True)` (or `ATTACH DATABASE 'file:...?mode=ro' AS src`). Because `market.db` is never written to by the warehouse, `warehouse_etl.py` can run on a cron schedule (e.g., immediately after `refresh.py` or hourly) and **cannot lock or corrupt** `market.db` while a parallel image-enrichment script updates `products.image_url` in `market.db`.
- **Automatic Image & GTIN Backfill Pickup**: When a parallel image-enrichment job populates `products.image_url` or `products.gtin` in `market.db`, the `row_hash = sha256(name || brand || gtin || image_url)` in Step 2 changes. Note that `input_signature_hash` (used for `silver_llm_cache`) depends only on `(clean_name, canonical_brand, amount, unit)`—**not** `image_url`. Therefore, newly enriched images automatically flow into `bronze_products_raw -> silver_products -> dim_product.image_url` **without invalidating the LLM categorization cache**.

### 6.2 CLI Interface & Flags (`scraping/warehouse_etl.py`)

```bash
venv/bin/python warehouse_etl.py [OPTIONS]

Options:
  --source-db PATH            Path to source SQLite DB (default: scraping/market.db)
  --warehouse-db PATH         Path to target warehouse DB (default: scraping/warehouse.db)
  --full-refresh              Re-process all Bronze/Silver/Gold tables from scratch (preserves silver_llm_cache & silver_category_review)
  --no-llm                    Skip LLM calls; use cached classifications + deterministic rule fallback only
  --llm-provider {ollama,openai_compat,gemini,none}
                              Override WAREHOUSE_LLM_PROVIDER env var
  --llm-model MODEL           Override model name (e.g. qwen2.5:7b-instruct)
  --max-llm-batches INT       Cap number of LLM batches per run for cost control (default: 50 = 1250 products)
  --export-review CSV_PATH    Export pending silver_category_review rows to CSV
  --import-review CSV_PATH    Import human-reviewed category overrides from CSV and re-sync Gold
  -v, --verbose               Enable INFO logging
```

### 6.3 Exact Function Signatures (`scraping/warehouse/etl.py`)

```python
@dataclass(frozen=True)
class ETLStats:
    new_attempts: int
    products_upserted: int
    price_observations_added: int
    canonical_groups: int
    llm_cache_hits: int
    llm_newly_classified: int
    review_queue_pending: int
    gold_products: int
    gold_current_offers: int
    duration_seconds: float

def run_etl(
    source_db_path: Path,
    warehouse_db_path: Path,
    classifier: Optional[ClassifierProvider] = None,
    full_refresh: bool = False,
    max_llm_batches: int = 50,
) -> ETLStats: ...
```

### 6.4 Step-by-Step Incremental & Idempotent Pipeline

Each run executes inside explicit database transactions per layer:

1. **Step 0 — Schema & Seed Initialization (`init_warehouse_db`)**:
   - Executes `warehouse/schema.sql`.
   - Upserts the static taxonomy tree (`taxonomy.TAXONOMY_TREE`) into `dim_category`, the unknown brand row (`brand_key = 1, brand_slug = 'desconhecida', brand_name = 'Sem Marca'`) into `dim_brand`, and initial brand alias dictionary into `silver_brand_aliases`.

2. **Step 1 — Bronze Incremental Ingestion (`ingest_bronze`)**:
   - Reads `last_scrape_attempt_id` from `etl_watermarks` (`0` on first run or `--full-refresh`).
   - **Scrape Attempts**: Copies `src.scrape_attempts WHERE id > :last_id` into `bronze_scrape_attempts` (`ON CONFLICT(attempt_id) DO NOTHING`).
   - **Products**: Reads all rows from `src.products`, computes `row_hash = sha256(name, brand, gtin, image_url)`, and upserts into `bronze_products_raw` only where `source_product_id` is new or `row_hash != existing.row_hash` (updating `last_seen_at`).
   - **Prices & Unpacked Binary History (Backfill + Incremental)**:
     - First, reads `src.price_history` and runs `unpack_history(blob)` (`struct.Struct(">II").iter_unpack`) to extract every historical `(price_cents, epoch)` pair in the 20-entry ring buffer. Inserts into `bronze_prices_log` with `record_origin = 'price_history_blob'` and `ON CONFLICT(source_product_id, source_store_id, observed_at_epoch, price_cents) DO NOTHING`.
     - Second, reads `src.prices` (where `price > 0`), converts `scraped_at` to UTC unix seconds and `round(price * 100)` to `price_cents`, and inserts into `bronze_prices_log` with `record_origin = 'prices_current'` (`ON CONFLICT ... DO UPDATE SET run_id = excluded.run_id, stock = excluded.stock, offer_label = excluded.offer_label, regular_price_cents = excluded.regular_price_cents`).
     - This guarantees both **complete backfill of existing `price_history` blobs** on day 1 and **unbounded retention** going forward (even after `market.db`'s 20-item ring buffer rolls over).

3. **Step 2 — Silver Normalization & Cross-Chain Entity Resolution (`build_silver_products`)**:
   - For every row in `bronze_products_raw` whose `row_hash` changed (or all rows when group membership could shift due to a new product/GTIN):
     - Computes `clean_name = clean(raw_name)`, `display_name = display_name(raw_name)`, `(amount, unit, pack_count) = parse_size(raw_name)`, `tokens = match_tokens(raw_name)`, `rule_category = categorize(raw_name)`, `rule_subcategory = subcategorize(raw_name)`, and `normalized_gtin = normalize_gtin(raw_gtin)`.
     - Resolves `canonical_brand`: checks `silver_brand_aliases` against `clean(raw_brand)`; if `raw_brand` is null, checks if any token in `clean_name` matches a known multi-chain brand in `silver_brand_aliases` or shares a GTIN with a branded product (`brand_of_gtin` logic from `public_api.py` line 487).
   - Runs `matcher.resolve_canonical_keys(silver_rows)`:
     - Groups products by `normalized_gtin` first, then by `(frozenset(tokens), (amount, unit, pack_count))` (including the unsized `(1, 'un', pack)` attachment rule from `public_api.py::match_products()`).
     - Assigns `canonical_product_key` (`gtin:...`, `tok:...`, or `raw:...`), `match_method`, and `input_signature_hash`.
     - Upserts all rows into `silver_products`.

4. **Step 3 — Silver LLM Categorization & Review Queue (`classify_silver_products`)**:
   - Queries `silver_products` for distinct `input_signature_hash` values that do not exist in `silver_llm_cache` for `PROMPT_VERSION`.
   - If `classifier` is enabled, slices missing signatures into batches of 25 (up to `max_llm_batches`), calls `classifier.classify_batch()`, and inserts valid responses into `silver_llm_cache`.
   - Evaluates the review rules (Section 5.2): any `canonical_product_key` with `confidence < 0.70`, invalid taxonomy slug, high-confidence rule disagreement, or `rule_category == 'Outros'` (when LLM is skipped) is upserted into `silver_category_review` (`ON CONFLICT(canonical_product_key) DO NOTHING` if already resolved by a human).

5. **Step 4 — Gold Dimensions & Bridges (`sync_gold_dimensions`)**:
   - **`dim_date`**: Ensures every calendar date present in `bronze_prices_log.observed_at_iso` (converted to `America/Fortaleza` `UTC-3`) exists in `dim_date`.
   - **`dim_store` & `dim_location`**: Deduplicates `src.stores` by `name` (picking `MIN(id)` as `canonical_source_id`), attaches `site_key` from `SCRAPER_MAP`, computes `active_run_id` using `public_api._listed_runs()`, and syncs `src.store_locations` into `dim_location`.
   - **`dim_brand`**: Inserts any new `canonical_brand` values from `silver_products` (and `silver_llm_cache.extracted_brand` when `silver_products.canonical_brand` was null and `confidence >= 0.80`).
   - **`dim_product` & Bridges**:
     - For each unique `canonical_product_key` in `silver_products`:
       - Elects the best representative name using `public_api._display_product()`'s ranking key `(size != (1, 'un'), not isupper(), len(name))`.
       - Picks the first non-null `gtin`, `image_url`, and `canonical_brand` across all group members (mirroring `_first_of()` and `photo_of_gtin` in `public_api.py`).
       - Checks if any member's `tok:...` key was previously stored in `dim_product.canonical_product_key` and has now been promoted to `gtin:...`; if so, updates `canonical_product_key` in-place on that `product_key` and saves `previous_canonical_key`.
       - Resolves `primary_category_key` via the Priority 1/2/3 waterfall (Section 5.2) and upserts `dim_product`, `bridge_product_source`, and `bridge_product_category`.

6. **Step 5 — Gold Facts (`sync_gold_facts`)**:
   - **`fact_price_observation`**: Inserts new rows from `bronze_prices_log` joined to `bridge_product_source`, `dim_product`, `dim_store`, and `dim_date`. Computes derived metrics:
     - `price_per_kg_or_l_cents = round(price_cents * 1000 / total_base_amount)` when `unit IN ('g', 'ml')` and `total_base_amount > 0`, else `NULL`.
     - `price_per_unit_cents = round(price_cents / pack_count)`.
     - Splits club vs. ordinary effective prices using `_CLUB_RE`.
   - **`fact_current_offer`**: Truncates and rebuilds `fact_current_offer` inside the transaction from `src.prices` filtered to each store's `dim_store.active_run_id` (exact parity with `build_public()`'s `merged` dict), computing cross-chain window metrics (`is_cheapest_for_product`, `chain_count_for_product`, `spread_pct_vs_cheapest`).
   - Updates `etl_watermarks` with the max `attempt_id` and `last_status = 'ok'`.

---

## (7) Testing Plan (`scraping/tests/test_warehouse.py`)

All tests run via `venv/bin/python -m unittest discover -s tests` with **zero network access**, **zero LLM API calls**, and **zero touches to the real `scraping/market.db` or `scraping/warehouse.db`** (using `tempfile.TemporaryDirectory()` for two isolated SQLite files: `source.db` and `warehouse.db`).

### 7.1 Fixtures & `FakeClassifier`
- **Source Fixture Builder (`_seed_source_db(source_path)`)**:
  - Creates a temporary `source.db` using `models.Base.metadata.create_all()`.
  - Seeds duplicate `Store` rows for `"Pinheiro"` (`id=1` and `id=5`, reproducing the real seed duplication bug), `"Pão de Açúcar"` (`id=2`), and `"Centerbox"` (`id=3`).
  - Seeds `StoreLocation` branches for Pinheiro (`id=1`).
  - Seeds `ScrapeAttempt` rows including both a healthy run (`items_found=100, run_id='run_ok'`) and a degraded partial run (`items_found=5, run_id='run_partial'`, below `MIN_SHARE_OF_USUAL = 0.25`).
  - Seeds cross-chain `Product` rows:
    1. `"LASANHA SADIA BOLONHESA 600G"` (Pinheiro, no GTIN, no brand) + `"Lasanha Bolonhesa Sadia Pacote 600g"` (Pão de Açúcar, `gtin='7893000444555'`, `brand='Sadia'`).
    2. `"Ração Úmida Whiskas Sachê Frango ao Molho 85g"` (a known failure case for keyword `categorize()`, which falsely matches `"frango"` -> `"Carnes e peixes"`).
    3. `"Produto Misterioso XYZ 500g"` (triggers `"Outros"` in `categorize()` and low confidence in LLM).
  - Seeds `Price` rows (including a `"PinClube"` offer with `regular_price`) and packed 8-byte `PriceHistory` blobs created with `scraper_service.pack_entry()`.
- **`FakeClassifier` Implementation**:
  - Deterministic in-memory `ClassifierProvider` that returns pre-configured `ProductClassificationResult` objects by matching substrings, records `calls: List[List[str]]` (so tests can assert exact batch counts and cache hit behavior), and can be configured to return low confidence (`0.42`) or malformed taxonomy slugs (`"non-existent/slug/here"`).

### 7.2 Mandatory Test Assertions
1. **`test_referential_integrity_and_no_orphan_facts`**:
   - Runs `PRAGMA foreign_key_check` on `warehouse.db` and asserts 0 violations.
   - Asserts `SELECT COUNT(*) FROM fact_price_observation f LEFT JOIN dim_product p ON f.product_key = p.product_key WHERE p.product_key IS NULL` is `0` (and same for `dim_store`, `dim_category`, `dim_brand`, `dim_date`).
2. **`test_row_counts_and_price_history_blob_unpacking`**:
   - If a product has 1 current price in `prices` and 3 packed historical entries in `price_history.blob`, asserts `fact_price_observation` contains exactly 4 rows for that `(source_product_id, store_key)` with the exact unpacked UTC timestamps and cent values.
   - Asserts duplicate `Store` rows (`id=1` and `id=5` for `"Pinheiro"`) collapse to 1 `dim_store` row (`canonical_source_id = 1`), and prices attached to either `store_id` map to that single `store_key`.
3. **`test_idempotency_and_llm_cache_zero_repayment`**:
   - Runs `run_etl()` once with `FakeClassifier`: asserts `len(fake_classifier.calls) == 1` and `stats.llm_newly_classified > 0`.
   - Runs `run_etl()` a second time against the unchanged `source.db`: asserts `len(fake_classifier.calls) == 1` (zero new calls made), `stats.llm_cache_hits > 0`, and row counts across all `dim_*` and `fact_*` tables are strictly unchanged.
4. **`test_image_enrichment_does_not_invalidate_llm_cache`**:
   - Updates `Product.image_url = "https://cdn.example.com/lasanha.jpg"` in `source.db` (simulating the parallel image-enrichment work).
   - Re-runs `run_etl()`: asserts `dim_product.image_url` is updated to the new URL while `len(fake_classifier.calls)` does **not** increase.
5. **`test_canonical_key_stability_across_market_db_rebuild`**:
   - Records ` {canonical_product_key: product_key}` from `dim_product`.
   - Deletes `source.db`, recreates it with the products inserted in **reverse order** (so every `products.id` in `source.db` changes), and re-runs `run_etl()`.
   - Asserts every `canonical_product_key` and its surrogate `product_key` in `dim_product` remain 100% identical, and `bridge_product_source` remaps the new `source_product_id`s to the existing `product_key`s.
6. **`test_late_arriving_gtin_promotes_key_without_duplicating_dim_product`**:
   - First run: two chains list `"Café Santa Clara 250g"` without GTIN -> gets `tok:<hash>` and `product_key = K`.
   - Second run: one chain backfills `gtin = "7896005800010"` -> asserts `dim_product` still has 1 row with `product_key = K`, `canonical_product_key = "gtin:07896005800010"`, and `previous_canonical_key = "tok:<hash>"`.
7. **`test_category_coverage_fallback_and_review_queue`**:
   - Asserts 100% of `dim_product` rows have a valid `primary_category_key`.
   - Asserts `"Ração Úmida Whiskas Sachê Frango ao Molho 85g"` (classified by `FakeClassifier` with `confidence=0.99` into `pet-e-bazar/pet-shop/racao-pet`) overrides the naive keyword rule (`"Carnes e peixes"`).
   - Asserts `"Produto Misterioso XYZ 500g"` (`confidence=0.42`) falls back to `rule_fallback` and inserts a `pending` row in `silver_category_review` with `reason_code = 'low_confidence'`.

---

## (8) Rollout Order, Risks, and What NOT to Do

### 8.1 Incremental Rollout Order

Each phase is independently testable and leaves the live app unaffected:

1. **Phase 1 — Foundation, DDL & Static Taxonomy (No LLM required)**
   - Create `scraping/warehouse/config.py`, `scraping/warehouse/db.py`, `scraping/warehouse/schema.sql`, and `scraping/warehouse/taxonomy.py`.
   - Verify `init_warehouse_db()` creates `warehouse.db` cleanly and populates `dim_category` (all ~110 L3 nodes mapped to legacy UI categories) and `dim_brand`.
2. **Phase 2 — Bronze Ingestion & Silver Normalizer/Matcher**
   - Implement `scraping/warehouse/normalizer.py` (reusing `clean`, `display_name`, `parse_size`, `match_tokens`, `categorize`, `subcategorize` from `services/public_api.py` and `unpack_history` from `services/scraper_service.py` by direct import so rules never drift) and `scraping/warehouse/matcher.py` (`canonical_product_key` & GTIN/token bridging).
   - Implement Bronze + Silver steps in `scraping/warehouse/etl.py` and `--no-llm` mode in `scraping/warehouse_etl.py`.
3. **Phase 3 — Gold Star Schema Population & Core Tests**
   - Implement Gold dimension, bridge, and fact loaders (`dim_date`, `dim_store`, `dim_location`, `dim_product`, `fact_price_observation`, `fact_current_offer`).
   - Run `warehouse_etl.py --no-llm` against a copy of `scraping/market.db` and run `tests/test_warehouse.py` for Phases 1–3.
4. **Phase 4 — Swappable LLM Classifier & Review Queue Workflow**
   - Implement `scraping/warehouse/classifier.py` (`OllamaClassifier`, `OpenAICompatClassifier`, `GeminiClassifier`, `FakeClassifier`) and `scraping/warehouse/exporter.py` (`--export-review` / `--import-review`).
   - Run initial classification backfill (`warehouse_etl.py --llm-provider ollama` or `--llm-provider gemini`), inspect `silver_category_review`, and verify `"Outros"` rate drops from ~10% to `< 1%`.
5. **Phase 5 — Scheduling & Optional Analytical/UI Integration**
   - Schedule `venv/bin/python warehouse_etl.py` as a separate cron/systemd post-hook after `refresh.py` (so `refresh.py`'s exit code and runtime are never impacted by warehouse ETL).

### 8.2 Key Risks & Mitigations

| Risk | Impact | Concrete Mitigation |
| :--- | :--- | :--- |
| **1. Variable-weight internal barcodes (`2xxxxxxxxxxxx`) colliding across chains** | Chain A's internal PLU `2000000000105` (Picanha) matches Chain B's `2000000000105` (Queijo Coalho). | `normalizer.py::normalize_gtin()` rejects any 13-digit code starting with `"2"` (GS1 variable-measure prefix) and forces Tier 2 (`tok:...`) matching. |
| **2. Unsized flyer items bridging two sizes** | Flyer item `"Cerveja Heineken"` merges 269ml and 350ml groups. | Preserve `public_api.py::match_products()`'s exact single-candidate rule: an unsized `(1, 'un', pack)` product only joins a token bucket if that bucket has **strictly one** size for `pack`; otherwise it gets its own `(0, 'un', pack)` key. |
| **3. LLM hallucinating non-existent category slugs or stalling ETL** | Foreign key failures on `dim_category` or slow/hanging HTTP requests. | Enforce strict JSON schema in request payload, a 30-second HTTP timeout per batch, and Python-side validation against `taxonomy.VALID_SLUGS`. Invalid slugs or timeouts never fail the ETL; they log a warning, route to `silver_category_review`, and fall back to `categorize()`. |
| **4. SQLite lock contention with `refresh.py` or parallel image enrichment** | `sqlite3.OperationalError: database is locked` during concurrent scrapes or image updates. | Open `market.db` strictly with URI `file:...?mode=ro` and copy Bronze delta tables in fast `< 200ms` reads before running any Silver/LLM/Gold work on `warehouse.db`. Enable `PRAGMA journal_mode = WAL` on `warehouse.db`. |
| **5. `price_history` ring-buffer overflow between sparse ETL runs** | If a product changes price >20 times between two warehouse ETL runs, the 21st oldest change is evicted from `market.db`. | Run `warehouse_etl.py` right after each `refresh.py` execution (every 12 hours per `SCRAPE_INTERVAL_HOURS`), where at most 1 price change per product/store can occur per run. |

### 8.3 What NOT to Do (Anti-Patterns to Avoid)

1. **DO NOT alter `scraping/market.db`, add columns to `scraping/models/product.py`, or write LLM categories back into `market.db`**:
   - Keeping `market.db` purely operational ensures scrapers and `refresh.py` stay fast, simple, and free of warehouse/LLM failure modes.
2. **DO NOT embed `warehouse_etl.py` inside `refresh.py` or `services/publish.py`**:
   - `refresh.py` is on the critical path for pushing fresh prices to the live Cloudflare/Neon production site. A slow local Ollama model or warehouse analytical rebuild must never delay or block `refresh.py`.
3. **DO NOT use `market.db` `products.id` or `prices.id` as primary/foreign keys in Gold fact tables**:
   - Only `bridge_product_source` and `bronze_*` should know about `source_product_id`. All Gold analytical queries must join on `product_key` (backed by `canonical_product_key`).
4. **DO NOT include `image_url` or volatile timestamps in `input_signature_hash` for `silver_llm_cache`**:
   - Image URLs are enriched asynchronously in parallel and CDN URLs change frequently; including them in the LLM cache key would trigger unnecessary duplicate LLM calls for already-classified products.
5. **DO NOT fork or copy-paste `clean()`, `parse_size()`, `match_tokens()`, `categorize()`, or `unpack_history()`**:
   - Import them directly from `services.public_api` and `services.scraper_service` inside `warehouse/normalizer.py` so any bugfix to size parsing or token stop-words automatically applies to both the live API and the warehouse.
