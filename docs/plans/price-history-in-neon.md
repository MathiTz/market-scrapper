# Plan: price history in Neon, so the site can show how a price moves

## Where we are (measured on `market.db`, 26/10/2026)

- Everything lives in `scraping/market.db`, a 6 MB SQLite file on one Mac: 12,061 products, 12,382 rows in
  `prices` (the current price of a product at a store), 4,070 rows in `price_history`. It is git-ignored and
  has no backup.
- `price_history` (`models/price_history.py`, packed by `services/scraper_service.py`) keeps a price that was
  *superseded*, as `(price in cents, when it was last seen at that price)`, 8 bytes each, capped at 20 per
  product and store. A price that is merely reconfirmed adds nothing. Today: 10,230 points, the oldest from
  6/9/2026, 4,012 of the 12,060 priced products with at least one.
- Neon holds only `snapshots` (`scraping/db/schema.sql`): the last 5 published `/api/public` payloads, as text.
  No history is published, and nothing in the UI reads it.

So the history exists, but only on one laptop, capped, and invisible. A lost or rebuilt `market.db` loses it.

## What we want

For a product at a store: its price over time (a small chart on the product page, "baixou R$ 0,50 desde
12/10" on a card), without making the published snapshot heavier.

## Design: append price points to Neon when they change

Not a copy of `market.db`. Fluctuation needs one row each time a price is seen at a new value.

```sql
-- scraping/db/schema.sql, next to snapshots (the publisher writes it, the API reads it)
CREATE TABLE IF NOT EXISTS price_points (
    product_key  TEXT        NOT NULL,   -- md5 of the lower-cased product name (see "The key")
    store        TEXT        NOT NULL,   -- chain name, as in stores.name
    observed_at  TIMESTAMPTZ NOT NULL,   -- when the store was last seen at this price
    price_cents  INTEGER     NOT NULL,
    regular_price_cents INTEGER,
    PRIMARY KEY (product_key, store, observed_at)
);
```

- **The key.** Not the local `products.id`: those restart if `market.db` is rebuilt, and the id the site shows
  for a matched product is its group's lowest member id, which shifts when a lower-id member joins. A product's
  name is what the scrapers already identify it by (`_get_or_create_product`), so `product_key` is a hash of
  the normalised name, and the store is the chain name. Stable across rebuilds and across re-matching.
- **Write path.** A step in `services/publish.py`, after the snapshot passes `check_snapshot` and is written:
  send the points (archived history entries plus each product's current price) that Neon does not have yet,
  `INSERT ... ON CONFLICT DO NOTHING`, so running it twice is harmless and a failed publish just catches up on
  the next one. It sends only the last few days once the backfill has run.
- **Backfill.** Once, from `price_history` and `prices`: about 14,000 points back to 6/9/2026.
- **Read path.** Each published offer gains a short `price_key` (the key of the member product whose price it
  is: about +80 KB on today's payload). The Worker serves `GET /api/price-history?keys=a,b,c` from
  `price_points` (`api/src/store.ts` gets a second reader; the read-only role needs `GRANT SELECT` on the
  table), cached like `/api/public`. The Flask API gets the same route (`AGENTS.md`: keep both in step).
- **UI.** A chart per store on the product page, and a "baixou/subiu desde" line on cards, fetched when the
  product opens - not in the snapshot.

What a chart can honestly say: each point is "seen at this price at this time"; a flat stretch has no points,
so the line is drawn at the last price up to the next point (or up to now). It cannot tell when a price first
appeared, only when it was last confirmed.

## Size

Changes are rare: 10,230 points in about 50 days is roughly 200 a day, so about 75,000 rows a year, a few MB.
It fits the free tier with room, and being append-only it lifts the 20-per-pair cap that `market.db` has.

## Considered and left out

- **Point `DATABASE_URL` at Neon** (the ORM would accept it). The save loop does about four queries per entry
  for ~12,000 entries: ~48,000 round trips over the internet per run, which turns a 1-minute save into most of
  an hour, and it needs batching to fix. Revisit only if the scraper moves next to the database.
- **Publish the history inside the snapshot.** It would multiply a payload the browser already loads whole.
- **One row per scrape per product.** ~8,000 rows a day for no extra information over "on change".

## Separate and cheap: protect `market.db` itself

History in Neon covers prices, not the rest (products, store locations, scrape attempts). A nightly
`sqlite3 market.db ".backup"` copied to R2 or iCloud closes that. Independent of everything above.

## Order of work, each step useful on its own

1. The `price_points` table and the idempotent sync in the publisher, with the backfill. Verify the row count
   against `price_history` and that a second run adds nothing. *(Writes to the production Neon: needs a go.)*
2. `price_key` on offers, and the Worker/Flask route with a test.
3. The chart on the product page, then the "mudou" line on cards.
4. The `market.db` backup.

## Open questions

- Keep the history forever, or prune past a year? At this size, forever is fine.
- A product renamed by a store gets a new key and a new history. Acceptable, or alias by GTIN when both
  names carry one?
- Also record flyer prices (Cometa), or only catalogue prices? Flyers are valid for a date range, not "seen".
