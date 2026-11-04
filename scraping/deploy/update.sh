#!/usr/bin/env bash
# Nightly: bring the server's checkout up to date with main (read-only deploy key, fast-forward only), and its
# Python packages when requirements.txt changed. Never touches market.db or .env.
set -euo pipefail
cd /opt/market-scrapper
before=$(git rev-parse HEAD)
git pull --ff-only --quiet
after=$(git rev-parse HEAD)
if [ "$before" != "$after" ] && ! git diff --quiet "$before" "$after" -- scraping/requirements.txt; then
  echo "requirements.txt changed: installing"
  scraping/venv/bin/pip install -q -r scraping/requirements.txt
fi
echo "code: ${before:0:7} -> ${after:0:7}"
