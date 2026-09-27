#!/usr/bin/env bash
# One command to refresh the live site: test, scrape every chain, store, validate, publish, deploy.
#
#   ./release.sh                     # everything
#   ./release.sh --no-deploy         # data only - the site always reads the newest published snapshot,
#                                    #   so a deploy is only needed when web/ or api/ code changed
#   ./release.sh --only atacadao     # any other flag goes straight to scraping/refresh.py
#                                    #   (--skip-scrape, --no-publish, --force, --sync-locations, ...)
#   SKIP_TESTS=1 ./release.sh        # skip the test gate
#
# Any step failing stops the run: refresh.py exits non-zero when validation blocks the publish (empty,
# broken or much-smaller snapshot), so a bad scrape never reaches the deploy.
set -euo pipefail
cd "$(dirname "$0")"

# Run a command silently; show its output only if it fails.
quiet() { local out; out=$("$@" 2>&1) || { echo "$out"; return 1; }; }

deploy=1
args=()
for arg in "$@"; do
  if [ "$arg" = "--no-deploy" ]; then deploy=0; else args+=("$arg"); fi
done

if [ "${SKIP_TESTS:-}" != 1 ]; then
  echo "==> tests"
  (cd scraping && quiet venv/bin/python -m unittest discover -s tests -t .)
  if [ "$deploy" = 1 ]; then
    (cd web && quiet npm run typecheck && quiet npm test -- --run)
    (cd api && quiet npm run typecheck && quiet npm test)
  fi
fi

echo "==> scrape, store, validate, publish"
(cd scraping && venv/bin/python refresh.py ${args[@]+"${args[@]}"})

if [ "$deploy" = 1 ]; then
  echo "==> deploy"
  (cd api && npm run deploy)
fi

echo "==> done"
