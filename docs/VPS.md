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
| `market-release.service` / `.timer` | `refresh.py` (scrape every chain, validate, publish, sync price history and catalogue) at 06:00 and 18:00 Fortaleza time |
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
   `systemctl daemon-reload` and `systemctl enable --now exit-tunnel market-release.timer market-locations.timer market-discovery.timer market-update.timer`.
7. **First run by hand**, to see it work: `systemctl start market-release` and `journalctl -fu market-release`.

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
