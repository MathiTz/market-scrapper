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

-- ---------------------------------------------------------------------------------------------
-- Accounts (written by the Hono API, not by the publisher). The API's public read role cannot write
-- these: point ACCOUNTS_HYPERDRIVE at a connection whose role may INSERT/UPDATE/DELETE here.

-- Shoppers. `password_hash` is null for an account that only ever signed in with Google; `google_sub`
-- is Google's stable subject id. The e-mail is stored lower-cased (the API normalises it).
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT,
    name          TEXT,
    google_sub    TEXT        UNIQUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL)
);

-- Opaque session tokens: the row keeps only the SHA-256 of the cookie value.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT        PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_expires ON sessions (expires_at);

-- One row per shopper: the place they compare prices from ("Perto de você") and the city they browse.
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id        UUID        PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    region         TEXT        NOT NULL DEFAULT 'Fortaleza',
    location_label TEXT,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    radius_km      SMALLINT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shopping lists kept in the account, so they follow the person between devices. `lines` has the same
-- shape as the browser's localStorage list: [{product_id, name, quantity, checked}, ...].
CREATE TABLE IF NOT EXISTS saved_lists (
    id         UUID        PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       TEXT        NOT NULL,
    lines      JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saved_lists_user ON saved_lists (user_id, updated_at DESC);
