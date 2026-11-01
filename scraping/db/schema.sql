-- Schema of the cloud database (Postgres). The Python publisher writes it; the Hono API reads it.
-- Keep both sides in step: api/src/store.ts selects exactly these columns.

-- Each row is one published copy of the /api/public payload, stored as text so the API can send it
-- without parsing it. Only the latest few rows are kept (the publisher prunes older ones).
CREATE TABLE IF NOT EXISTS snapshots (
    id           BIGSERIAL PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    etag         TEXT        NOT NULL,  -- hash of the payload without its generated_at
    payload      TEXT        NOT NULL
);

-- One row each time a product is seen at a price at a chain: the history behind the price chart. Append-only
-- and written by services/price_points.py after a publish; a price that did not change adds nothing.
-- product_key is md5 of the lower-cased product name (stable across rebuilds of the local database).
CREATE TABLE IF NOT EXISTS price_points (
    product_key         TEXT        NOT NULL,
    store               TEXT        NOT NULL,  -- chain name
    observed_at         TIMESTAMPTZ NOT NULL,  -- when the chain was seen at this price
    price_cents         INTEGER     NOT NULL CHECK (price_cents > 0),
    regular_price_cents INTEGER,
    PRIMARY KEY (product_key, store, observed_at)
);

-- Every product the local database has ever stored, keyed like price_points (md5 of the lower-cased name), so a
-- price history can always be read back as a product even after no chain lists it. Written by
-- services/catalogue.py after a publish; first_seen/last_seen are when any chain was first/last seen selling it.
CREATE TABLE IF NOT EXISTS products (
    product_key TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,  -- as the chain prints it
    brand       TEXT,
    category    TEXT        NOT NULL,
    subcategory TEXT        NOT NULL DEFAULT '',
    amount      INTEGER     NOT NULL,  -- grams or millilitres per pack; 1 when the name states no size
    unit        TEXT        NOT NULL CHECK (unit IN ('g', 'ml', 'un')),
    pack_count  INTEGER     NOT NULL DEFAULT 1,
    gtin        TEXT,                  -- EAN/GTIN when a chain's source gave one
    image_url   TEXT,
    first_seen  TIMESTAMPTZ NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS products_gtin ON products (gtin) WHERE gtin IS NOT NULL;
