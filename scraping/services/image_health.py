"""Whether the image URL a chain gave still resolves.

The payload's ``image_url`` points at the chain's CDN, and those files do not last: a delisted
product, a re-upload under a new name, or a bucket that stops answering for everyone
(``assets.ibecom.com.br`` returns 403 for every one of its 478 images). The UI has no fallback, so a
dead URL is a card saying "Sem foto".

The publisher therefore checks each URL and, when it is dead *and* the local mirror has a verified
copy of that product's photo, publishes ``/images/<path>`` instead. Those mirror files ship with the
Worker (``web/scripts/sync-images.mjs``), so the image the page shows is one we host ourselves.

Answers are cached by URL in ``data/image-health.json``: ``build_public`` runs per request, and a
network check per product per request would be absurd. A missing cache means "no opinion", and the
remote URL is published unchanged - the same behaviour as before this module existed.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

from config import BASE_DIR

logger = logging.getLogger(__name__)

CACHE_FILE = BASE_DIR / "data" / "image-health.json"
TTL_DAYS = 7
# A dead host answers every image the same way; the UA only avoids the trivial blocks.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/156.0.0.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}
_DEAD_CODES = {403, 404, 410, 451}
# Hosts that can never serve a product photo. They come from tests (a fixture once wrote
# "http://img.example/nescau.jpg" into market.db) and must never reach the payload, whatever a cache says.
PLACEHOLDER_HOSTS = frozenset({
    "img.example", "example.com", "example.org", "example.net", "localhost", "127.0.0.1", "0.0.0.0",
})

_CACHE: Dict[str, object] = {"stamp": None, "entries": {}}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load(path: Optional[Path] = None) -> Dict[str, dict]:
    """``{url: {"ok": bool|None, "at": iso}}``, reloaded when the file changes."""
    target = Path(path or CACHE_FILE)
    try:
        stat = target.stat()
    except OSError:
        return {}
    stamp = (str(target), stat.st_mtime_ns, stat.st_size)
    if _CACHE["stamp"] == stamp:
        return _CACHE["entries"]  # type: ignore[return-value]
    try:
        entries = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = {}
    _CACHE["stamp"] = stamp
    _CACHE["entries"] = entries
    return entries


def save(entries: Dict[str, dict], path: Optional[Path] = None) -> None:
    target = Path(path or CACHE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entries, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    _CACHE["stamp"] = None  # next load reads the new file


def is_placeholder(url: Optional[str]) -> bool:
    """Whether the URL points at a documentation/test host rather than a real image."""
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return (host in PLACEHOLDER_HOSTS or host.endswith(".example") or host.endswith(".test")
            or host.endswith(".invalid"))


def check(url: str, timeout: float = 8.0) -> Optional[bool]:
    """True when the URL serves an image, False when it is definitely gone, None when unsure."""
    if is_placeholder(url):
        return False
    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(url, method=method, headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status < 400:
                    return True
        except urllib.error.HTTPError as error:
            if error.code in _DEAD_CODES:
                return False
            if error.code >= 500:
                return None
        except Exception:  # noqa: BLE001 - a timeout or DNS failure is "unsure", not "dead"
            continue
    return None


def _entry(ok: Optional[bool]) -> dict:
    return {"ok": ok, "at": _now().strftime("%Y-%m-%dT%H:%M:%SZ")}


def _is_stale(entry: Optional[dict], ttl_days: int = TTL_DAYS) -> bool:
    if not entry:
        return True
    try:
        checked = datetime.fromisoformat(str(entry.get("at")).replace("Z", "+00:00"))
    except ValueError:
        return True
    # An "unsure" answer is retried sooner than a definite one.
    age = _now() - checked
    return age > timedelta(days=1 if entry.get("ok") is None else ttl_days)


def refresh(urls: Iterable[str], workers: int = 16, path: Optional[Path] = None) -> Dict[str, dict]:
    """Check every URL, keep what was already known, and write the cache."""
    entries = dict(load(path))
    wanted = sorted({url for url in urls if url and url.startswith(("http://", "https://"))})
    if not wanted:
        return entries

    def run(url: str) -> tuple:
        return url, check(url)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for url, ok in pool.map(run, wanted):
            entries[url] = _entry(ok)
    save(entries, path)
    return entries


def ensure_fresh(urls: Iterable[str], limit: Optional[int] = None, workers: int = 16,
                 path: Optional[Path] = None) -> int:
    """Re-check the stale URLs only. Returns how many were checked; never raises."""
    try:
        entries = load(path)
        stale = [url for url in dict.fromkeys(urls)
                 if url and url.startswith(("http://", "https://")) and _is_stale(entries.get(url))]
        if limit is not None:
            stale = stale[:limit]
        if not stale:
            return 0
        refresh(stale, workers=workers, path=path)
        return len(stale)
    except Exception as error:  # noqa: BLE001 - publishing must not fail over an image check
        logger.warning("image health check skipped: %s", error)
        return 0


def is_dead(url: Optional[str], entries: Optional[Dict[str, dict]] = None) -> bool:
    """Whether a known-dead URL should be replaced. Unknown URLs are left alone."""
    if not url:
        return False
    if is_placeholder(url):
        return True
    entry = (entries if entries is not None else load()).get(url)
    return bool(entry) and entry.get("ok") is False


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check the product image URLs and cache the answers.")
    parser.add_argument("--all", action="store_true", help="re-check every URL, not just the stale ones")
    parser.add_argument("--limit", type=int, help="stop after N checks")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--status", action="store_true", help="report the cache and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    entries = load()
    if args.status:
        dead = sum(1 for e in entries.values() if e.get("ok") is False)
        alive = sum(1 for e in entries.values() if e.get("ok") is True)
        print(f"{len(entries)} URL(s) known: {alive} ok, {dead} dead, {len(entries) - alive - dead} unsure")
        return 0

    from models.database import SessionLocal, init_db
    from models.product import Product

    init_db()
    db = SessionLocal()
    try:
        urls = [p.image_url for p in db.query(Product).all() if p.image_url]
    finally:
        db.close()
    checked = refresh(urls, workers=args.workers) if args.all else None
    if checked is None:
        count = ensure_fresh(urls, limit=args.limit, workers=args.workers)
        print(f"checked {count} stale URL(s)")
    else:
        print(f"checked {len(checked)} URL(s)")
    entries = load()
    dead = sum(1 for e in entries.values() if e.get("ok") is False)
    print(f"{len(entries)} URL(s) known, {dead} dead")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
