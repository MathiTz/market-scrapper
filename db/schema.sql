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
