# Product images: what we have, what's missing, how we fill the gap

## Where images come from today

| Source | Image? | Why |
| --- | --- | --- |
| VTEX stores (`scraper/vtex.py`) | **Yes** | The VTEX catalog API returns `items[].images[].imageUrl`; `_image_url()` picks the first one and `ProductPrice.image_url` carries it through. |
| Flyer / OCR sources (`scraper/flyer_ocr.py`, centerbox, frangola, ...) | **No** | OCR reads price/name text off a page or PDF. There is no per-product photo in the source. |
| Plain HTML scrapers | **No** | Selectors extract name/price; no image field is captured. |

So the gap is structural, not a bug: VTEX products arrive with an image, everything
else arrives with `image_url = NULL`.

A second, subtler part of the gap is in the write path. `_get_or_create_product()`
in `services/scraper_service.py` is intentionally conservative — it will not clobber a
value an earlier source found — but that also means **nothing ever goes looking for a
missing image later**. A product that first appears via a flyer stays imageless
forever, even if a VTEX source scrapes the same GTIN the next day.

## The fix: `services/image_enrichment.py`

A backfill service that runs *after* scraping and only touches products whose
`image_url` is empty. Two stages, cheapest and most reliable first:

1. **GTIN lookup** (`resolve_by_gtin`) — if the product has a valid barcode, query
   Open Food Facts by GTIN. A barcode match is exact, so it is trusted at
   confidence `1.0`. No key, no browser, no scraping.
2. **Name search** (`resolve_by_search`) — otherwise search by `brand + name` and
   accept a candidate only when `name_similarity()` clears
   `min_name_similarity` (default `0.62`). Similarity takes the better of a raw
   `SequenceMatcher` ratio and a token-set ratio, so word reordering
   ("Leite Ninho 380g" vs "Ninho Leite 380g") still matches while an unrelated
   product is rejected.

Guarantees:

- **Idempotent** — `enrich_product()` returns early if `image_url` is already set, so
  re-running is safe and cheap.
- **Never destructive** — it only ever writes into an empty field.
- **Resumable** — `enrich_missing()` commits every `commit_every` (default 25)
  products, so a crash keeps the images found so far.
- **Fail-soft** — a network error or non-200 is logged at debug level and reported as
  `"no match found"` for that product; the run continues.

## Running it

```bash
cd scraping

python backfill_images.py --dry-run          # list products missing an image
python backfill_images.py --limit 200 --delay 0.5
python backfill_images.py --ids 12,34,56
python backfill_images.py --json             # machine-readable summary
```

`--delay` sleeps between HTTP requests; set it to ~0.5s for a large run to stay
polite to Open Food Facts. Exit code is `0` for a completed run (even if some
products found nothing) and `1` only on an unexpected error.

## Tests

`tests/test_image_enrichment.py` — 17 tests, no network and no database (fake HTTP
session + fake SQLAlchemy session). Covers GTIN hits/misses, non-numeric GTINs
skipping the network, close vs weak name matches, candidates without images,
GTIN-over-search preference, the no-overwrite guarantee, batch commits, and the
empty-id-list short circuit.

```bash
cd scraping && python -m unittest tests.test_image_enrichment -v
```

## Verified behaviour

- `--dry-run` against the real database lists the actual gap (products #137-#141,
  all L'OR coffee capsules, `gtin=NULL`) — confirming the missing images are
  exactly the non-VTEX/flyer products.
- A live run against the real DB with a local mock of the OFF endpoint matched
  product #137 at **0.969 confidence** and persisted the image, then reverted.
- **Open Food Facts returned HTTP 503 during testing** (`Page temporarily
  unavailable`). The service degraded correctly — logged at debug level, reported
  as `no match found`, exit code 0 — but real-world hit rates depend on OFF
  availability. Add retry-with-backoff and a second provider (follow-ups 2 and 3)
  before running a large backfill.

## Suggested follow-ups

1. **Capture images at scrape time where they exist.** The HTML scrapers should pull
   `og:image` / `srcset` when the page has one, so the backfill has less to do.
2. **Cache lookups.** A `product_image_lookup` table keyed by GTIN would avoid
   re-querying OFF for the same barcode across runs.
3. **Widen the sources.** Open Food Facts covers groceries well; Open Beauty Facts
   and Open Products Facts cover the rest of the same catalog. A chain of providers
   behind one interface would raise the hit rate.
4. **Surface coverage.** Add a `products_with_image / products_total` gauge to the
   published snapshot so the gap is visible instead of silent.
