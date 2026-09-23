<p align="center">
  <img src="mercado-em-dia-ui/public/icon.svg" width="88" height="88" alt="Mercado em Dia" />
</p>

<h1 align="center">Mercado em Dia</h1>

<p align="center">
  Scrapes Brazilian grocery chains in Fortaleza, matches the same product across stores, and serves a fast,
  searchable price-comparison site.
</p>

## What this is

Three parts, one product:

1. **The scrapers** (Python, this repo's root) collect prices, deals, flyers and real store branches from
   seven chains, store them locally, and publish a validated snapshot to the cloud.
2. **The API** (`api/`, a Hono app on Cloudflare Workers) serves that snapshot to the browser - read-only,
   no scraping logic of its own.
3. **The UI** (`mercado-em-dia-ui/`, React + Vite) loads the whole snapshot once and does search, filtering
   and sorting client-side. Shopping lists live in the browser's `localStorage`, not a database.

```
your machine: scrapers -> market.db -> python -m services.publish -> Neon Postgres <- Hono API (Cloudflare) <- browsers
```

There used to be a fourth part - a server-rendered Flask + Bootstrap + Folium UI (shopping lists, a CEP
radius search with a map) - that predates the React UI and duplicated what it now does better. It has been
removed; `web/app.py` today only serves JSON (the local API the UI talks to in development, plus scrape/
health/diagnose endpoints), no HTML pages.

## Features

- Scrapes **every product**, not a fixed list, from Pão de Açúcar, Sam's Club, Mercadinho São Luiz,
  Carnaúba Supermercados, Cometa, Pinheiro Supermercado and Atacadão - each site's own quirks handled in
  `scraper/sites/` (see *How each site is scraped* below).
- Matches the same product across chains by name, strictly (precision over recall: a false match would
  show a wrong "cheapest").
- Derives category **and subcategory** from the product name ("Hidratante" and "Sabonete" instead of one
  shared "Higiene e beleza"), and the real per-kg/L/unit price - including for fresh meat and produce sold
  by weight ("Maminha Bovina ... Kg"), which have no fixed pack size to parse from a number.
- Real brand, barcode (GTIN/EAN) and product photo, pulled for free from the VTEX-backed chains' own API
  responses (Atacadão, Sam's Club) - not guessed, not scraped from anywhere extra.
- Real physical branches per chain (not one placeholder address), each with real coordinates where the
  source gives them; the UI resolves every offer to the *nearest* branch to wherever you are.
- Deal-aware: regular price, discount label, and club-only (member) prices are all tracked and shown
  separately from what everyone pays.
- Flyers (Cometa's `encartes`) read with OCR, kept only when a printed discount badge confirms the reading.
- One row per (product, store) in the database, not one per scrape - past prices are archived into a
  compact, capped binary history instead of growing the table forever (this project scrapes ad-hoc, not on
  a guaranteed schedule, so the data layer is built to not care how often or how irregularly it runs).
- Scheduled scraping at fixed clock times (6:00 and 12:00) via APScheduler, so it fires at the same times
  of day regardless of when the process itself was last started.
- Automatic retry with backoff, scrape-attempt monitoring, and a validation gate before anything publishes
  (an empty, broken, or much-smaller-than-usual snapshot never goes live - the previous good one stays).

## Tech stack

- **Scraping/backend:** Python 3.14, SQLAlchemy (SQLite locally, Postgres in production), Flask (local API
  only), Scrapling (stealth fetching) with Selenium as a fallback, APScheduler.
- **UI:** React 19, Vite, TypeScript, TanStack React Query - see `mercado-em-dia-ui/AGENTS.md`.
- **API:** Hono on Cloudflare Workers, reading Postgres (Neon) through Hyperdrive - see `api/`.

## Project structure

```
market_scrapper/
├── config.py                  # Central configuration (env vars)
├── refresh.py                 # Scrape + validate + publish, one command
├── scheduler.py                # Runs refresh.py at 6:00 and 12:00 daily
├── run.py                      # Local Flask API entry point
├── seed.py                     # Seeds the chains as Store rows (idempotent)
├── migrate_price_history.py    # One-off: compacts old per-scrape price rows into history blobs
├── scraper/
│   ├── base.py                 # Base scraper class (retry logic, ProductPrice/BranchLocation)
│   ├── vtex.py                 # Shared scraper for VTEX-backed stores (Atacadão, Sam's Club)
│   ├── mercadapp.py            # Shared scraper for the "Mercadapp" platform (Mercadinho, Carnaúba)
│   ├── scrapling_scraper.py    # Scrapling-based base scraper (stealth mode)
│   ├── flyer_ocr.py            # Cometa flyer OCR + badge verification
│   └── sites/                  # One thin file per chain
├── models/                     # SQLAlchemy models (Product, Store, StoreLocation, Price, PriceHistory, ...)
├── services/
│   ├── public_api.py           # Builds the /api/public payload the UI expects
│   ├── scraper_service.py      # Bridge between scrapers and the database (upsert + history)
│   ├── store_locations.py      # Syncs real physical branches per chain
│   ├── address_search.py       # Geocoding for real branches and the UI's "Perto de você"
│   └── publish.py              # Publishes a snapshot to the cloud Postgres
├── web/app.py                  # Local JSON API (mirrors api/ for local dev) + scrape/health/diagnose
├── api/                        # Hono app on Cloudflare Workers (production API)
├── mercado-em-dia-ui/          # React + Vite front end
├── db/                         # Postgres schema + read-only role setup for the cloud database
├── tests/                      # Python test suite (unittest)
├── diagnose_sites.py           # Checks site reachability & product extraction
├── setup_chromedriver.py       # Installs/fixes chromedriver for the Selenium fallback
└── requirements.txt
```

## Quick start (local development)

One-time setup, from the project root (zsh or bash):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup_chromedriver.py
cp .env.example .env
python -m models.database
python -m seed                                  # stores only; safe to repeat
(cd mercado-em-dia-ui && npm ci)                # the UI; needs Node 24+
```

Load prices once (a few minutes):

```bash
venv/bin/python -c "from services.scraper_service import run_all_offers; print(run_all_offers())"
```

Then run three processes, each in its own terminal tab:

| Tab | Command | What it is |
|-----|---------|------------|
| 1 | `HOST=127.0.0.1 venv/bin/python run.py` | Local JSON API on http://127.0.0.1:5050 |
| 2 | `cd mercado-em-dia-ui && npm run dev` | the UI on **http://127.0.0.1:3000** (`/demo` for fictional data) |
| 3 | `venv/bin/python scheduler.py` | refreshes prices at 6:00 and 12:00 daily |

Start tab 1 before opening the UI - it reads its data from the API. `HOST=127.0.0.1` keeps Flask (which
runs in debug mode) reachable only from your machine; put it in `.env` to make that permanent.

### Other ways to run a scrape

```bash
venv/bin/python refresh.py                 # scrape everything, validate, publish - one command
venv/bin/python refresh.py --only atacadao sams_club   # just these chains
venv/bin/python refresh.py --skip-scrape   # re-validate and re-publish what's already stored
python -m unittest discover -s tests       # the test suite
```

`refresh.py`'s validation never lets a broken or much-smaller-than-usual snapshot go live - see the table
in *What a store's list is* below for exactly what it checks.

## Configuration

Centralized in `config.py`, overridable via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///market.db` |
| `PUBLISH_DATABASE_URL` | Cloud Postgres (Neon) the scheduler publishes to | *(unset = don't publish)* |
| `DEFAULT_QUERY` | Default search term for scraping (empty = all products) | `""` |
| `DEFAULT_LIMIT` | Max results per site | `1000` |
| `SCRAPE_INTERVAL_HOURS` | Used to derive how long an offer stays "current" (3x this) | `12` |
| `SCRAPE_MAX_RETRIES` | Max retry attempts for network errors | `3` |
| `SCRAPE_RETRY_BACKOFF` | Base backoff seconds between retries | `2.0` |
| `SCRAPE_TIMEOUT` | HTTP timeout in seconds | `15` |
| `SECRET_KEY` | Flask secret key | `dev-secret` |
| `HOST` | Flask host | `0.0.0.0` |
| `PORT` | Flask port | `5050` |
| `DEBUG` | Flask debug mode | `true` |

## Production: Neon + Cloudflare

Scraping stays on your machine (retail sites block datacenter IPs, not home ones). After each scrape the
data goes to a cloud database, and a small read-only API on Cloudflare serves it.

- **Python** derives everything (matching products across chains, categories, subcategories, club prices,
  flyers) and stores the finished `/api/public` payload as one row of the `snapshots` table
  (`db/schema.sql`). Publishing unchanged data is a no-op, and only the newest 5 snapshots are kept.
- **`api/`** is the Hono app. It streams the latest snapshot untouched (with `ETag` and `Cache-Control`),
  answers `POST /api/location` (address search through Photon) and serves the built UI from the same
  Worker. It is read-only.
- **The UI** downloads the snapshot once and searches and filters it in the browser; shopping lists stay in
  `localStorage`.

### One-time setup

1. **Neon** (console.neon.tech): create a project (region São Paulo, Postgres 17). In *Connect*, copy the
   direct (not pooled) connection string into `.env` as `PUBLISH_DATABASE_URL=...`. Never commit it.
2. **Publish once:** `venv/bin/python -m services.publish` creates the table and uploads the data. From
   then on the scheduler publishes after every scrape.
3. **Read-only role for the API:** edit the password in `db/readonly_role.sql`, run it in Neon's SQL
   editor, and note that role's connection string (the API must not use the owner's).
4. **Cloudflare:** `cd api && npm install && npx wrangler login`, then
   `npx wrangler hyperdrive create mercado-em-dia --connection-string="<read-only connection string>"` and
   put the id it prints in `api/wrangler.jsonc`.
5. **Deploy:** `cd api && npm run deploy` (builds the UI, then deploys the Worker with the UI's files and
   the API together).

### Develop and test

- **API locally:** `cd api && WRANGLER_HYPERDRIVE_LOCAL_CONNECTION_STRING_HYPERDRIVE='postgresql://user:password@host/db' npm run dev`
  (port 8787). Point the UI at it with `cd mercado-em-dia-ui && API_URL=http://127.0.0.1:8787 npm run dev`.
- **API tests:** `cd api && npm test` (no database or Cloudflare needed) and `npm run typecheck`.
- **UI tests:** `cd mercado-em-dia-ui && npm test` and `npm run typecheck`.
- **Python tests:** `python -m unittest discover -s tests` from the repo root.
- **Without the cloud at all:** `run.py` (Flask) serves the same `/api/public` shape for local development.

## What a store's list is

What a store sells changes from one scrape to the next: new products appear and others are dropped. So the
published list for each store is **whatever its latest complete scrape run found**, not everything ever
seen:

- **Added:** a product in the newest run shows up right away.
- **Removed:** a product that was in an earlier run but not in the newest one disappears from the
  published data at once (it is not left "current" until its freshness timer runs out).
- **Safe against bad runs:** a run that failed, found no items, or found under **25%** of the items the
  store usually has (measured against its best recent runs) is set aside. The previous list stays, with the
  note "A última coleta trouxe poucos itens; mostrando a anterior." A broken or partial scrape therefore
  cannot empty a store.
- **How it works:** each scrape run gets an id (`run_id`) saved on its attempt and on every price it
  stored.

`refresh.py`'s own validation, on top of the above:

| Finding | Level | What happens |
|---------|-------|---------------|
| A chain's scrape failed, found nothing, or found far fewer items than usual | warning | that chain's previous list stays; the rest is published |
| A chain has no offers in the snapshot | warning | reported |
| No chain produced fresh data | error | nothing is published |
| The snapshot is empty, or has offers without a valid price or product | error | nothing is published |
| The snapshot has under half the offers of the live one | error | nothing is published |

Errors leave the live data untouched. Publishing identical data twice is a no-op ("Nothing new").

## How each site is scraped

### Cometa Supermercados (`cometasupermercados.com.br/encartes`)

Cometa publishes its offers as **flyers (encartes)** shown as a carousel of banner images. The page fills
the carousel from a public JSON endpoint, so the scraper calls it directly instead of rendering the page:

1. `GET /api/encartes` returns each flyer's name, validity description, cover image and PDF.
2. Those paths are relative (`/uploads/...`) and only exist on the CMS host, so they are **resolved to
   `https://adminx.cometasupermercados.com.br/uploads/...`**.
3. The flyers are flat images (the PDFs have no text layer), so each cover is **read with EasyOCR**
   (`scraper/flyer_ocr.py`).

**OCR is optional.** Install it with `pip install -r requirements-ocr.txt` (pulls in PyTorch; the first run
downloads the OCR model, ~2 minutes; a full run over ~8 flyers takes 2-3 minutes on CPU). Without it,
`CometaScraper.scrape()` logs a warning and returns no products.

**Only verified prices are kept.** OCR of stylised price tags is unreliable on its own. Many flyers print a
discount badge next to each product ("23% DE DESCONTO", "De: 6,49", "Por: 4,99"), so an offer is accepted
only when `round((1 - por / de) * 100)` matches the badge (within 1 point). A gross misread breaks that
equation and the offer is dropped - flyers with no badge currently yield nothing, and a one-cent slip on an
expensive item can still pass the check. Misread sizes are repaired when the shape is unmistakable
(`20Og` → `200g`, `Jko`/`lkg`/`1ko` → `1kg`, `scraper/flyer_ocr.py`'s `fix_units`).

### Mercadinho São Luiz and Carnaúba Supermercados (the "Mercadapp" platform)

Both run the same storefront platform, sharing `scraper/mercadapp.py`'s `MercadappScraper`; the two site
files only set the chain's own `base_url`, `offers_url` and `brand_id`.

It is a React SPA that loads its offers as JSON but renders only a fraction of them on screen. The scraper
opens the offers page with Selenium and injects a script *before* the page's own code runs, capturing every
offers response the page receives - name, price, regular price, discount, stock and offer dates. It falls
back to reading the rendered cards if nothing is captured.

**Real branches:** `fetch_locations()` opens the storefront's own "Clique e Retire" dialog and captures the
response it triggers - every real branch's name and address (no coordinates; geocoded separately, see
*Real store branches*).

### Pão de Açúcar (`paodeacucar.com`)

The offers are on the **home page**, in lazy-loaded carousels, behind a bot check. The scraper renders the
page with Scrapling's stealth browser, scrolls to trigger the lazy sections, finds each product by its
`/produto/<id>/<slug>` link, and reads the regular price, deal label and per-unit price from the card text.

### Pinheiro Supermercado (`lojaonline.pinheirosupermercado.com.br/ofertas`)

A client-rendered Angular app; the endpoint behind it (`.../produtos/em-oferta?page=N`) holds every offer
(~900), not just the ~20 rendered on screen. Scrapling opens `/ofertas` (the page logs itself in as a
guest), then a page action reads that endpoint from *inside* the page with its own session and headers.
Prices tagged **PinClube** are member-only and stored with `PinClube` in the deal label.

### Atacadão and Sam's Club (`atacadao.com.br`, `samsclub.com.br`)

Both run on **VTEX**, so they share `scraper/vtex.py` and call the public product-search API instead of
rendering pages - which also gives, for free in the same response: brand, EAN/GTIN barcode and a product
photo (see *Features* above).

Atacadão sells at everyday wholesale prices with no discounts, so it collects a plain price list. Sam's
Club reads pages sorted by discount and stops at the first non-discounted product, so only real offers are
collected.

**Real branches:** VTEX's own public pickup-points API returns real branches with real coordinates already
- no geocoding needed, unlike the Mercadapp chains.

## Real store branches

A chain sells through **several physical branches**, not one, and each is often kilometres from the others.
`models/store_location.py`'s `StoreLocation` (one row per real branch, several sharing a chain's `Store`
row) and `services/store_locations.py`'s `sync_store_locations()` track this properly:

- Each scraper implements `fetch_locations() -> List[BranchLocation]` (see above for how each platform does
  it). VTEX's pickup-points API, Cometa's "Onde Estamos" API and Pão de Açúcar's store-locator file give
  real coordinates directly; the Mercadapp chains and Pinheiro's "Nossas Lojas" page give only a text
  address, geocoded via `services/address_search.py`.
- Branches change rarely, so a run that finds far fewer than are already known is treated as partial and
  nothing is deleted.
- `build_public()` publishes them as a `retailer_locations` array, separate from `offers`. The UI resolves
  each offer's **nearest** branch to whatever reference point is active, rather than trusting one fixed
  point. A chain with no known branches yet has none in the array; the UI shows "endereço não informado"
  rather than a guess.

```bash
venv/bin/python refresh.py --sync-locations
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'scrapling'`** - `pip install scrapling` or
`python install_scrapling.py`.

**`ModuleNotFoundError` for a Scrapling transitive dep** (`playwright`, `camoufox`, etc.) -
`pip install scrapling --upgrade`, or `pip uninstall scrapling -y && pip install scrapling`.

**`SessionNotCreatedException` / chromedriver not found** - `python setup_chromedriver.py`; if that fails,
`brew install chromedriver`, or diagnose with `python diagnose_chromedriver.py`.

**`TypeError: Can't replace canonical symbol for '__firstlineno__'`** (Python 3.14) - your SQLAlchemy is
too old: `pip install --upgrade SQLAlchemy`.

**Port 5050 or 3000 already in use** - `lsof -nP -iTCP:5050 -sTCP:LISTEN` (or 3000), then `kill <PID>`. To
change the API's port permanently, set `PORT` in `.env` and start the UI with
`API_URL=http://127.0.0.1:<port> npm run dev`.

**The UI shows no prices, or "Não foi possível atualizar"** - the API isn't running or the database is
empty. Check `http://127.0.0.1:5050/api/public`, then load prices (see *Quick start*).

**Database already exists and you want a fresh one:**

```bash
rm market.db
python -m models.database
python -m seed
```

**Sites not reachable / no products found** - run `python diagnose_sites.py` then
`python analyze_diagnostics.py`; results are saved to `diagnostics/*.json`.

**Scraping fails with network errors** - there's automatic retry with backoff (`SCRAPE_MAX_RETRIES`,
`SCRAPE_RETRY_BACKOFF`). Check `http://127.0.0.1:5050/scrape/status` for which sites are failing and why.

## License

MIT
