# Running the pipeline on a server

The scrape, validation and publish run unattended on a VPS (Hetzner, Helsinki) on a timer, instead of from a
laptop. This is what is deployed and how to rebuild it. Secrets (the Neon connection string, SSH keys) live only on
the servers and are never in the repository.

## What runs where

| Machine | Role |
|---|---|
| **VPS** (Ubuntu 24.04) | Scheduler, all scrapers, easyocr for Cometa's flyers, publish to Neon, nightly code update |
| **Exit node** (Linode, São Paulo) | Only an SSH server. The VPS opens a SOCKS tunnel to it so chains that refuse a foreign datacenter address are reached from a Brazilian one |
| **Neon** | The published snapshot, price history and catalogue the Worker reads |
| **A laptop** | `./release.sh` still deploys the Worker and UI (needs the Cloudflare login); it should not publish data once the VPS does |

Why the exit node: Atacadão answers 403 and Pão de Açúcar does not connect from the Helsinki address, but both answer
from a Brazilian one. Which chains go through it is set per chain with `PROXY_<CHAIN>` in `.env`
(`scraper/base.py`); the others connect directly.

## Files in `scraping/deploy/`

| File | What it does |
|---|---|
| `exit-tunnel.service` | Keeps `ssh -D 127.0.0.1:1081` to the exit node up, restarting it if it drops |
| `market-catalogue.service` / `.timer` | `refresh.py --full --only carnauba mercadinho gbarbosa sams_club atacadao` on Sundays at 02:00 Fortaleza time: the whole catalogue of the chains that have one (4,000 to 8,000 products each, over an hour in all). Each chain's run becomes its list for the week |
| `market-release.service` / `.timer` | `refresh.py --skip atacadao` (scrape every chain's offers, validate, publish, sync price history and catalogue) at 06:00 and 18:00 Fortaleza time. The chains with a whole catalogue read only their deals here and lay them over the weekly list, putting ended deals back to the regular price; Atacadão has no deals, so only the weekly run reads it |
| `market-locations.service` / `.timer` | `refresh.py --skip-scrape --sync-locations` at 07:00 and 19:00 Fortaleza, one hour after each release, so the branch lookup never shares the machine with a scrape |
| `market-discovery.service` / `.timer` | `python -m services.store_discovery` on Sundays at 08:00 Fortaleza: looks on OpenStreetMap for supermarket chains we have no scraper for and saves them in `candidate_chains` (not published) |
| `market-update.service` / `.timer` / `update.sh` | `git pull --ff-only` at 23:30, plus `pip install` when `requirements.txt` changed |

## Setting a server up

1. **Packages and code.** `apt-get install -y python3.12-venv sqlite3 git`. Create a GitHub *deploy key* (read-only) for
   the repository and clone to `/opt/market-scrapper`.
2. **Python.** In `scraping/`: `python3 -m venv venv && venv/bin/pip install -r requirements.txt`, then the browser
   (`venv/bin/scrapling install`). For Cometa's flyer OCR install the CPU build of torch first
   (`pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`), then
   `pip install -r requirements-ocr.txt`. The packages are pinned (`scrapling`, `camoufox`, `rebrowser-playwright`):
   newer ones rename options Scrapling 0.2.99 still sends and the browser does not start.
3. **Exit node.** A Linode (or any VPS) in São Paulo with a firewall that allows SSH only from the server and your own
   address, password login off. On the VPS create a key for the tunnel and authorize it on the exit node restricted to
   forwarding: `no-pty,no-agent-forwarding,no-X11-forwarding,command="/bin/false" ssh-ed25519 ...`.
4. **`.env`** in `scraping/` (copy `.env.example`): `PUBLISH_DATABASE_URL` and the four `PROXY_` lines. Type the
   connection string yourself on the server.
5. **Database.** Copy `market.db` once from the machine that last held it, with a consistent copy
   (`sqlite3 market.db ".backup /tmp/copy.db"`, then `scp`) so branch locations, store rows and price history carry
   over. **Only one machine may publish**: stop any other scheduler (`scheduler.py` on a laptop) first.
6. **Units.** `cp scraping/deploy/*.service scraping/deploy/*.timer /etc/systemd/system/`, then
   `systemctl daemon-reload` and `systemctl enable --now exit-tunnel market-release.timer market-catalogue.timer market-locations.timer market-discovery.timer market-update.timer`.
7. **First run by hand**, to see it work: `systemctl start market-release` and `journalctl -fu market-release`.

## Receipt OCR (optional)

"Conferir com o cupom" reads a receipt photo with `POST /api/receipt/ocr`, which needs OpenCV and the vision
provider's key, so it runs here and the Worker forwards to it (`api/src/app.ts`: per-address rate limit, 10 MB cap,
shared secret). The path is Worker -> Caddy (HTTPS, only that route) -> gunicorn on `127.0.0.1:5051`.

1. Packages: `scraping/venv/bin/pip install -r requirements.txt -r requirements-ocr.txt` (gunicorn is in the first).
2. `.env` in `scraping/`: `OLLAMA_API_KEY=` (the provider key) and `OCR_SHARED_SECRET=` (make one with
   `openssl rand -hex 24`). Without the secret the route is open to anyone who reaches it.
3. Caddy (`apt install caddy`), then `scraping/deploy/Caddyfile.ocr` as `/etc/caddy/Caddyfile` with `HOST` replaced by
   the server's address in sslip.io form (`203.0.113.7` -> `203-0-113-7.sslip.io`, no domain needed). Ports 80 and 443
   must be open (Caddy gets its certificate on 80), here and in the provider's firewall.
4. `cp scraping/deploy/market-ocr.service /etc/systemd/system/`, `systemctl daemon-reload`,
   `systemctl enable --now market-ocr`.
5. On the Worker (from `api/`): `npx wrangler secret put OCR_URL` (`https://<HOST>`) and
   `npx wrangler secret put OCR_SECRET` (the same value as `OCR_SHARED_SECRET`), then `npm run deploy` (it builds the
   UI with `VITE_RECEIPT_OCR=1`).

6. Firewall (Hetzner Cloud): inbound 22 only from your own addresses, 80 open to everyone (Caddy gets and renews its
   certificate over it), and 443 only from Cloudflare's published ranges (https://www.cloudflare.com/ips-v4 and
   `ips-v6`; no "Any" source in that rule, or it allows everyone). The Worker's calls come from those ranges, so it still
   gets through, while a direct request to the server times out. If the OCR ever starts failing with 502 after months
   of working, compare the rule with those two lists first.

Check, from the server itself or before step 6: `curl -i -X POST https://<HOST>/api/receipt/ocr` answers 401 (the secret is required), any other path 404, and
`journalctl -u market-ocr -n 50` shows the requests. The Worker answers 501 until both secrets are set.

## Day to day

```
systemctl list-timers 'market-*'          # when each runs next
journalctl -u market-release -n 100       # the last release
journalctl -u market-update -n 20         # the last code update
systemctl is-active exit-tunnel           # the tunnel
```

A failed release leaves the live data untouched: validation refuses an empty, broken or much smaller snapshot. A chain
that fails keeps its last good prices until they pass their time to live (36 hours).

Branch locations run on their own timer an hour after each release (they geocode through Photon, which rate-limits).
To run them by hand: `venv/bin/python refresh.py --skip-scrape --sync-locations`.

## Finding new chains

`services/store_discovery.py` lists the supermarkets and wholesalers OpenStreetMap has for a region, drops those that match a
chain in `stores` (fuzzy name match, so "Mercadão São Luiz" is the São Luiz we have), groups the rest and keeps them in
`candidate_chains`, biggest first. It finds where a chain is, not its prices: a chain only appears in the app once it has
a scraper. For another region: `python -m services.store_discovery --state PE --city Recife Olinda`.

```
sqlite3 market.db "select branches, name, cities, status from candidate_chains where status='new' order by branches desc limit 20"
sqlite3 market.db "update candidate_chains set status='planned' where key='assai'"   # or 'ignored'
```

## Known limits

- **Centerbox's API** answers 429 (Cloudflare error 1015) for an address that has sent it many requests, whatever the
  client; it passes again after a while. Retry it before changing code.
- Cometa's 22 offers need easyocr; without it that chain returns no offers.
- The server is a single machine: if it is down, nothing is scraped, and the site keeps showing the last snapshot.
