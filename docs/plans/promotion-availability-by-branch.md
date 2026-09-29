# Plan: knowing which branch a price is actually good at

## The problem, precisely

Today a price is stored keyed to `(product_id, store_id)` (`models/price.py`), and `store_id` identifies a
**chain**, not a physical address — `models/store.py` says so explicitly: "one row per chain name, not per
physical branch." A chain's real branches live separately in `store_locations` (`models/store_location.py`),
populated by each scraper's `fetch_locations()` (see `services/store_locations.py`), but that table only
holds name/address/coordinates. Nothing connects a specific price observation to a specific branch.

The public API and the UI already know this is a simplification — the "Perto de você" screen says "Os preços
são do site de cada rede e podem variar na loja" (`app/main.tsx`'s nearby copy) — but that is a blanket
disclaimer, the same for every product and every branch. It cannot tell a shopper "yes, confirmed at the
branch nearest you" from "we have no idea if this applies where you are." That is the gap: **some prices we
collect are genuinely chain-wide (most VTEX catalog pricing looks metro-scoped per the comment in
`scraper/vtex.py`), and some are not** — Centerbox's prices come from exactly one store, its "Conceito"
branch (`seed.py`: "Real branches are not tracked for it yet (19 in Fortaleza); prices come from its Conceito
store"), and some Cometa flyers are already published per branch (a flyer titled "Cometa Guararapes" is not
the same offer as one for a different branch) — yet both are shown today as if they applied to every branch
of the chain uniformly.

## Proposed schema: `collection_addresses`

A new table recording, for a price we scraped, the specific branch(es) we have evidence it applies to. Kept
separate from `prices` rather than adding a column to it, because the relationship is genuinely
many-to-many-with-uncertainty: one scraped price can have zero branches confirmed (today's status quo -
nothing changes for it), one (the common case - Centerbox, a branch-specific flyer), or several (a regional
promo spanning some but not all of a chain's branches).

```python
class CollectionAddress(Base):
    """Evidence that a specific price we collected applies at a specific real branch.

    Absence of a row for a price is not evidence the price does *not* apply at a branch - most of what we
    collect today has no branch evidence at all and is shown chain-wide, as it always has been. A row here
    only ever narrows the claim from "the chain, somewhere" to "this branch, specifically" - it never
    contradicts the price itself.
    """
    __tablename__ = "collection_addresses"

    id = Column(Integer, primary_key=True)
    price_id = Column(Integer, ForeignKey("prices.id"), nullable=False)
    store_location_id = Column(Integer, ForeignKey("store_locations.id"), nullable=False)
    # How we know this branch is the right one - the same three-way split Offer.method already uses in the
    # public API, so the UI's existing "Coleta automática / Registro manual" language extends for free.
    method = Column(String, nullable=False)  # 'automatic' | 'manual' | 'reported' (a shopper said so)
    # What told us: e.g. "flyer title matched branch name 'Guararapes'", "store's own single storefront maps
    # 1:1 to its Conceito branch", "shopper report on <date>". Free text, shown as a tooltip, not parsed back.
    evidence = Column(String, nullable=True)
    collected_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("price_id", "store_location_id", name="uq_collection_address"),)
```

A price's own `scraped_at` plus the existing TTL/staleness rule (`offerState` in `web/lib/domain.ts`,
`ttl_hours`) already governs whether the *price* is stale; this table does not need its own separate
freshness clock — a row is only ever as fresh as the price it points to, and disappears when that price does
(cascade or a periodic prune keyed to the same run that would drop the price).

## Where the evidence comes from, cheapest first

1. **Single-branch chains, mapped once.** Centerbox is the clean case: its prices come from exactly one
   store, and that store's real address is knowable (its own "Conceito" branch, once `fetch_locations()`
   finds it - `seed.py` says branches are "not tracked for it yet", so this starts by fixing that). Every
   Centerbox price gets one `collection_addresses` row, written once at scrape time, `method='automatic'`.
   Zero new scraping - it is one join against branches we already fetch or will fetch.

2. **Flyers that already name a branch.** Cometa's `Encarte.name` sometimes *is* a branch name ("Guararapes"
   matches a `StoreLocation.name` of "Guararapes", per `scraper/sites/cometa.py`'s own branch-name cleanup,
   `"Loja Aldeota"` -> `"Aldeota"`). A name-similarity match (the same kind of scoring
   `services/image_enrichment.py`'s `name_similarity()` already does for product names - reusable, not a new
   idea) between a flyer's title and the chain's known branch names, above a confidence threshold, writes one
   row per matched offer, `method='automatic'`, `evidence` recording the matched branch name. A flyer whose
   title does not match any branch name (most of them, today) gets no row - it stays chain-wide, as now.
   Worth a quick pass across every chain's flyer titles first, not just Cometa's, to see how common this is.

3. **Everything else stays chain-wide, honestly.** VTEX and Mercadapp catalogs are not proven branch-specific
   (VTEX's own comment says pricing "seems metro-scoped", which is a *region*, not a branch) - forcing a
   branch match here would be guessing, which is worse than the current honest disclaimer. They get no rows
   for now. Getting real branch-level VTEX pricing would mean querying per pickup-point (`vtex.py` already
   fetches the pickup-points list for branch addresses; querying each one's price is a materially bigger
   scrape - one call per branch per product instead of one call per product - and belongs in a later stage,
   not this one.

4. **Stretch, later: shopper reports.** A "eu vi esse preço nesta loja" action on a product page writes a
   `method='reported'` row. Low confidence individually (one person, one visit), but several independent
   reports for the same branch are a real signal over time. This reuses the existing `Offer.method` UI
   pattern (`manual`/`automatic`/`demo` already render differently) and needs no new UI concept, only a form
   and a write endpoint - deliberately last, since it needs real usage to be worth building.

## What changes downstream

- **`services/public_api.py`**: `build_public()` already resolves `context_id`/`context_label` per store and
  ships `retailer_locations`. Add a `confirmed_branch_ids: str[]` (or similar) to each offer that has rows in
  `collection_addresses`, empty for everything else - additive, no existing field changes shape.
- **`web/lib/location.ts`**: `offerLocation()` already resolves the *nearest* branch to a reference point,
  purely for the distance line. Extend it to also say whether that nearest branch is in the offer's
  `confirmed_branch_ids` - three states to show, not two: "confirmed at the unit nearest you", "chain-wide,
  not confirmed for this unit" (today's disclaimer, now scoped down to only the offers that actually need it),
  and today's "no reference set" case, unchanged.
- **`components/offer-row.tsx` / `product-card.tsx`**: a small badge or word change on the existing distance
  line, not a new UI surface - "Confirmado na unidade Guararapes" next to the distance, instead of always the
  same generic caveat.
- No breaking change anywhere: an offer with no confirmed branches renders exactly as every offer does today.

## Sequencing

1. Migration: create `collection_addresses` (empty at first, nothing depends on it existing).
2. Backfill for Centerbox specifically (its own real branches, if not fetched yet - `fetch_locations()` may
   need writing first, per the `seed.py` comment) and re-check.
3. Name-match flyers with a branch-named title; measure how many offers actually get a row before building
   anything on top - if the count is tiny, the UI payoff (stage 4 below) is not worth doing yet.
4. Only once coverage is measured and non-trivial: extend `build_public()`, `location.ts`, and the two
   components above.
5. Shopper-reported evidence, once the confirmed-vs-not distinction is live and shoppers can see it (there is
   no point collecting reports the UI cannot yet show).

## Open questions to settle before writing code

- **Naming**: `collection_addresses` describes the table's *contents* (addresses collected), but the same
  name could be misread as "addresses we collect from" (websites/CDNs), which is not what it holds. Confirm
  the name before the migration ships, since renaming a live table later is its own small migration.
- **Prune policy**: a row should not outlive the price it points to. Decide whether that is a foreign-key
  cascade (simplest, automatic) or a periodic sweep alongside the existing price-history compaction
  (`scraper_service._upsert_price`'s `PriceHistory` packing already runs one).
- **Confidence threshold for the flyer name-match** (stage 2): reuse `image_enrichment.py`'s
  `min_name_similarity` default (0.62) as a starting point, or tune separately - branch names are short and a
  false match is more visible to a shopper (wrong store) than a wrong product photo is.
