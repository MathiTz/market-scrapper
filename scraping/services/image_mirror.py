"""Mirror product images locally, and verify the ones we had to go looking for.

Separate from ``refresh.py`` on purpose: scraping decides *what* a product costs, this decides what it
looks like, and one must be runnable without the other. It never changes ``products.image_url`` - the
scrape data stays the source of truth; the mirror lives in ``product_images`` and on disk under
``scraping/images/<xx>/<sha256>.webp`` (400 px WebP, content-addressed so the same photo shared by two
chains is stored once).

Flow per product:

1. The chain's own image URL. Trusted: it comes from the product's page, so it is not model-checked.
2. If that fails or is missing, a ladder of lookups - Open Food Facts by barcode, then by name, then
   another chain's catalogue search, then a web image search.
3. Every image from step 2 is checked by a local decision model (``d3``) before it is accepted. The
   question is split into criteria ("is this a package photo?", "does it show this product?", "is this
   the brand?") because a single yes/no cannot tell a wrong product from a right product with the
   wrong brand on the label.
4. Three rejected candidates and the product is flagged, keeping the first candidate for a human to
   look at, instead of guessing.

    python -m services.image_mirror --status
    python -m services.image_mirror --limit 50 --workers 8
    python -m services.image_mirror --product 1234 -v
    python -m services.image_mirror --retry-flagged
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import requests
from PIL import Image, ImageOps
from sqlalchemy import text

from config import BASE_DIR
from models import Product, ProductImage, SessionLocal, init_db
from services.image_enrichment import ProductImageEnricher, name_similarity

logger = logging.getLogger(__name__)

IMAGE_ROOT = Path(BASE_DIR) / "images"
TARGET_PX = 400
WEBP_QUALITY = 82
MIN_SIDE = 120           # anything smaller is an icon or a spacer, not a product photo
MAX_BYTES = 12_000_000
MAX_WEB_CANDIDATES = 3

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
D3_MODEL = os.getenv("D3_MODEL", "d3:2b")
D3_THRESHOLD = float(os.getenv("D3_THRESHOLD", "0.8"))

# VTEX chains expose the same product-search API the scrapers already use; searching it for a product
# we are missing a photo for often lands on the identical package, because it is the same catalogue.
VTEX_SEARCH = {
    "Atacadão": "https://www.atacadao.com.br/api/io/_v/api/intelligent-search/product_search",
    "Sams Club": "https://www.samsclub.com.br/api/io/_v/api/intelligent-search/product_search",
}


# --------------------------------------------------------------------------- download and prepare


def _http() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
    return s


def fetch_bytes(url: str, http: requests.Session, timeout: float = 15.0) -> Optional[bytes]:
    """The body at ``url`` when it looks like an image, else None. Never raises."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        response = http.get(url, timeout=timeout, allow_redirects=True, stream=True)
        if response.status_code != 200:
            return None
        # Chains serve images as image/*; a few CDNs say application/octet-stream. Trust the bytes
        # rather than the header, but refuse obvious HTML (a bot-check page disguised as an image).
        ctype = (response.headers.get("content-type") or "").lower()
        if ctype.startswith("text/") or "html" in ctype:
            return None
        data = response.content
    except Exception as exc:  # noqa: BLE001 - one bad URL must not abort the run
        logger.debug("fetch failed %s: %s", url, exc)
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    return data


def prepare(blob: bytes, min_side: int = MIN_SIDE) -> Optional[Tuple[bytes, int, int]]:
    """400 px WebP for ``blob``, or None when it is not a usable image.

    ``min_side`` is relaxed for operator-curated files: a tall, narrow packshot is a legitimate
    product photo even when it is under the size an automatic search result must meet.
    """
    try:
        image = Image.open(io.BytesIO(blob))
        image.load()
    except Exception:  # noqa: BLE001 - corrupt or mislabelled payload
        return None
    if image.width < min_side or image.height < min_side:
        return None
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((TARGET_PX, TARGET_PX), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=WEBP_QUALITY, method=4)
    return buffer.getvalue(), image.width, image.height


# --------------------------------------------------------------------------- candidate sources


@dataclass
class Candidate:
    kind: str           # openfoodfacts | chain_search | web_search
    source_url: str
    blob: bytes
    prepared: Tuple[bytes, int, int]


def openfoodfacts_candidates(product: Product, http: requests.Session) -> Iterator[Candidate]:
    enricher = ProductImageEnricher(session=http)
    for match in (enricher.resolve_by_gtin(product.gtin), enricher.resolve_by_search(product.name, product.brand)):
        if not match:
            continue
        blob = fetch_bytes(match.image_url, http)
        if not blob:
            continue
        ready = prepare(blob)
        if ready:
            yield Candidate("openfoodfacts", match.image_url, blob, ready)


def chain_search_candidates(product: Product, http: requests.Session) -> Iterator[Candidate]:
    """Ask another chain's catalogue for the same name; keep only a close name match."""
    for chain, endpoint in VTEX_SEARCH.items():
        try:
            response = http.get(endpoint, params={"query": product.name, "count": 3}, timeout=15)
            if response.status_code != 200:
                continue
            products = (response.json() or {}).get("products") or []
        except Exception:  # noqa: BLE001
            continue
        for entry in products:
            found = entry.get("productName") or ""
            if name_similarity(found, product.name) < 0.62:
                continue
            item = (entry.get("items") or [{}])[0]
            image = (item.get("images") or [{}])[0].get("imageUrl")
            blob = fetch_bytes(image, http)
            ready = prepare(blob) if blob else None
            if ready:
                logger.debug("%s: candidate from %s (%s)", product.name, chain, found)
                yield Candidate("chain_search", image, blob, ready)
                break


def _vqd(html: str) -> Optional[str]:
    found = re.search(r'vqd="([^"]+)"', html) or re.search(r"vqd=([\d-]+)", html)
    return found.group(1) if found else None


def _duckduckgo_images(query: str, http: requests.Session, limit: int) -> List[str]:
    try:
        landing = http.get("https://duckduckgo.com/", params={"q": query, "iax": "images", "ia": "images"}, timeout=15)
        token = _vqd(landing.text)
        if not token:
            return []
        payload = http.get(
            "https://duckduckgo.com/i.js",
            params={"l": "br-pt", "o": "json", "q": query, "vqd": token, "f": ",,,,,", "p": "1"},
            headers={"Referer": "https://duckduckgo.com/"},
            timeout=15,
        )
        if payload.status_code != 200:
            return []
        return [r.get("image") for r in (payload.json() or {}).get("results", []) if r.get("image")][:limit]
    except Exception:  # noqa: BLE001
        return []


def _bing_images(query: str, http: requests.Session, limit: int) -> List[str]:
    try:
        page = http.get("https://www.bing.com/images/search", params={"q": query}, timeout=15)
        if page.status_code != 200:
            return []
        found = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', page.text)
        return [u.replace("\\/", "/") for u in found][:limit]
    except Exception:  # noqa: BLE001
        return []


def web_search_candidates(product: Product, http: requests.Session) -> Iterator[Candidate]:
    query = " ".join(part for part in (product.name, product.brand) if part)
    urls = _duckduckgo_images(query, http, MAX_WEB_CANDIDATES)
    if len(urls) < MAX_WEB_CANDIDATES:
        urls += [u for u in _bing_images(query, http, MAX_WEB_CANDIDATES) if u not in urls]
    for url in urls[:MAX_WEB_CANDIDATES]:
        blob = fetch_bytes(url, http)
        ready = prepare(blob) if blob else None
        if ready:
            yield Candidate("web_search", url, blob, ready)


# --------------------------------------------------------------------------- decision model


def _ask_d3(questions: Dict[str, dict], state: str, webp: bytes) -> Optional[dict]:
    """Answers from the local decision model, or None when it is unreachable."""
    payload = {
        "model": D3_MODEL,
        "state": state,
        "images": [base64.b64encode(webp).decode("ascii")],
        "questions": questions,
    }
    try:
        response = requests.post(f"{OLLAMA_URL}/v1/systemone", json=payload, timeout=120)
        if response.status_code != 200:
            logger.warning("d3 answered HTTP %s: %s", response.status_code, response.text[:200])
            return None
        return response.json().get("answers")
    except Exception as exc:  # noqa: BLE001
        logger.warning("d3 unavailable: %s", exc)
        return None


def _criterion(instructions: str, yes: str, no: str) -> dict:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": yes, "false": no}}


def verify(product: Product, webp: bytes) -> Tuple[bool, dict]:
    """Does this image show *this* product from *this* brand? Returns (accepted, evidence)."""
    questions = {
        "is_package": _criterion(
            "Does the image show a photograph of a retail product package, bottle, box or label?",
            "It is a product package photo.",
            "It is a logo, an advertisement, a watermark, a person, or otherwise not a package.",
        ),
        "is_product": _criterion(
            f"Does the package in the image show the product described as '{product.name}'?",
            f"It is '{product.name}' or the same item with a different wording or size.",
            "It is a different product.",
        ),
    }
    if product.brand:
        questions["is_brand"] = _criterion(
            f"Is the brand '{product.brand}' visible on the package in the image?",
            f"The brand '{product.brand}' appears on the package.",
            f"The brand '{product.brand}' does not appear, or a different brand does.",
        )

    answers = _ask_d3(questions, state=f"Product: {product.name}. Brand: {product.brand or 'unknown'}.", webp=webp)
    if answers is None:
        return False, {"error": "decision model unavailable"}

    scores = {name: round(float((answers.get(name) or {}).get("noul") or 0.0), 4) for name in questions}
    accepted = all(score >= D3_THRESHOLD for score in scores.values())
    return accepted, {"model": D3_MODEL, "threshold": D3_THRESHOLD, "scores": scores}


# --------------------------------------------------------------------------- persistence


def save(db, product: Product, candidate: Candidate, status: str, decision: Optional[dict]) -> ProductImage:
    webp, width, height = candidate.prepared
    digest = hashlib.sha256(webp).hexdigest()
    relative = Path("images") / digest[:2] / f"{digest}.webp"
    absolute = Path(BASE_DIR) / relative
    try:
        absolute.parent.mkdir(parents=True, exist_ok=True)
        if not absolute.exists():
            absolute.write_bytes(webp)
    except OSError as exc:
        logger.error("could not write %s: %s", absolute, exc)

    row = db.query(ProductImage).filter(ProductImage.product_id == product.id).one_or_none()
    if row is None:
        row = ProductImage(product_id=product.id)
        db.add(row)
    row.sha256 = digest
    row.path = str(relative)
    row.width, row.height, row.bytes = width, height, len(webp)
    row.source_kind = candidate.kind
    row.source_url = candidate.source_url
    row.status = status
    row.decision = json.dumps(decision, ensure_ascii=False) if decision else None
    row.model = (decision or {}).get("model")
    return row


# --------------------------------------------------------------------------- per-product flow


@dataclass
class Outcome:
    product_id: int
    name: str
    status: str                  # ok | flagged | skipped | error
    kind: str = ""
    detail: str = ""
    candidate: Optional[Candidate] = None
    decision: Optional[dict] = None


def mirror_product(product: Product, http: requests.Session, verify_searched: bool = True) -> Outcome:
    """Resolve one product's image without touching the database."""
    name = product.name

    # 1) The chain's own image: trusted by provenance, so accepted without a model check.
    if product.image_url:
        blob = fetch_bytes(product.image_url, http)
        ready = prepare(blob) if blob else None
        if ready:
            return Outcome(product.id, name, "ok", "chain", "chain image",
                           Candidate("chain", product.image_url, blob, ready))

    # 2) Looked up elsewhere - every candidate must pass the decision model.
    tried = 0
    first: Optional[Candidate] = None
    for source in (openfoodfacts_candidates, chain_search_candidates, web_search_candidates):
        for candidate in source(product, http):
            if first is None:
                first = candidate
            tried += 1
            if not verify_searched:
                return Outcome(product.id, name, "ok", candidate.kind, "unverified", candidate)
            accepted, evidence = verify(product, candidate.prepared[0])
            if accepted:
                return Outcome(product.id, name, "ok", candidate.kind, "verified", candidate, evidence)
            if evidence.get("error"):
                # The model is down, not the image: leave the product unprocessed so a later run retries
                # instead of recording a rejection that never happened.
                return Outcome(product.id, name, "skipped", candidate.kind, evidence["error"])
            if tried >= MAX_WEB_CANDIDATES:
                break
        if tried >= MAX_WEB_CANDIDATES:
            break

    if first is not None:
        return Outcome(product.id, name, "flagged", first.kind, f"{tried} candidate(s) rejected", first,
                       {"result": "flagged", "candidates": tried})
    return Outcome(product.id, name, "flagged", "", "no image found")


# --------------------------------------------------------------------------- commands


def report() -> int:
    init_db()
    db = SessionLocal()
    try:
        total = db.query(Product).count()
        done = db.query(ProductImage).filter(ProductImage.status == "ok").count()
        flagged = db.query(ProductImage).filter(ProductImage.status == "flagged").count()
        print(f"products: {total} | mirrored: {done} | flagged: {flagged} | missing: {total - done - flagged}")
        print("\nby source:")
        rows = db.execute(
            text("select source_kind, status, count(*) from product_images group by source_kind, status order by 3 desc")
        ).fetchall()
        for kind, status, count in rows:
            print(f"  {kind:<14} {status:<8} {count:>5}")
        failing = db.query(ProductImage.source_kind, ProductImage.status).filter(ProductImage.status == "flagged").all()
        if failing:
            print("\nflagged by source:")
            counts: Dict[str, int] = {}
            for kind, _ in failing:
                counts[kind or "(none)"] = counts.get(kind or "(none)", 0) + 1
            for kind, count in sorted(counts.items(), key=lambda kv: -kv[1]):
                print(f"  {kind:<14} {count:>5}")
    finally:
        db.close()
    return 0


def run(limit: Optional[int] = None, product_id: Optional[int] = None, workers: int = 8,
        retry_flagged: bool = False, verify_searched: bool = True,
        source_url: Optional[str] = None) -> int:
    init_db()
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)

    if source_url:
        if product_id is None:
            print("--source-url needs --product: say which product the image belongs to.")
            return 2
        return _apply_manual(product_id, source_url)

    db = SessionLocal()
    try:
        query = db.query(Product)
        if product_id is not None:
            query = query.filter(Product.id == product_id)
        if retry_flagged:
            flagged = {row.product_id for row in db.query(ProductImage).filter(ProductImage.status == "flagged")}
            products = [p for p in query if p.id in flagged]
        else:
            done = {row.product_id for row in db.query(ProductImage)}
            products = [p for p in query if p.id not in done]
        if limit:
            products = products[:limit]
    finally:
        db.close()

    if not products:
        print("Nothing to do: every selected product already has an image record.")
        return 0
    print(f"mirroring {len(products)} product(s) with {workers} worker(s)")

    started = time.monotonic()
    counts = {"ok": 0, "flagged": 0, "error": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool, _writer() as write:
        futures = {pool.submit(_guard, product, verify_searched): product for product in products}
        for future in as_completed(futures):
            outcome = future.result()
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
            write(outcome)
            if count_done(counts) % 25 == 0:
                print(f"  {count_done(counts)}/{len(products)} "
                      f"(ok {counts['ok']}, flagged {counts['flagged']}) {time.monotonic() - started:.0f}s", flush=True)

    print(f"done in {time.monotonic() - started:.0f}s: "
          f"{counts['ok']} ok, {counts['flagged']} flagged, {counts['error']} errors")
    return 0


def _apply_manual(product_id: int, url: str) -> int:
    """Store an image the operator picked by hand.

    A human decision outranks the model: the image is kept even if the decision model would reject it,
    but the model's verdict is still recorded so the choice stays auditable.
    """
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product is None:
            print(f"No product with id {product_id}.")
            return 2
        http = _http()
        blob = fetch_bytes(url, http)
        ready = prepare(blob) if blob else None
        if not ready:
            print(f"Could not use {url}: not a usable image (blocked, too small, or not an image).")
            return 1
        candidate = Candidate("manual", url, blob, ready)
        _, evidence = verify(product, ready[0])
        save(db, product, candidate, "ok", evidence)
        db.commit()
        webp, width, height = candidate.prepared
        scores = evidence.get("scores") or {}
        verdict = ", ".join(f"{k}={v}" for k, v in scores.items()) or evidence.get("error", "not checked")
        print(f"Stored {width}x{height} px ({len(webp)} bytes) for '{product.name}' ({verdict}).")
        return 0
    finally:
        db.close()


def count_done(counts: Dict[str, int]) -> int:
    return counts.get("ok", 0) + counts.get("flagged", 0) + counts.get("error", 0) + counts.get("skipped", 0)


def _guard(product: Product, verify_searched: bool) -> Outcome:
    """Never let one product's failure stop the pool."""
    try:
        return mirror_product(product, _http(), verify_searched=verify_searched)
    except Exception as exc:  # noqa: BLE001
        logger.exception("image mirror failed for %s", product.name)
        return Outcome(product.id, product.name, "error", detail=str(exc)[:200])


class _writer:
    """Single-writer database access: SQLite takes one writer, so workers only fetch."""

    def __enter__(self):
        self.db = SessionLocal()
        return self

    def __call__(self, outcome: Outcome) -> None:
        if outcome.candidate is None or outcome.status == "skipped":
            return
        try:
            product = self.db.get(Product, outcome.product_id)
            if product is None:
                return
            save(self.db, product, outcome.candidate, outcome.status, outcome.decision)
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception("could not store image for product %s", outcome.product_id)

    def __exit__(self, *exc):
        self.db.close()
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mirror product images locally and verify searched ones.")
    parser.add_argument("--status", action="store_true", help="report coverage and exit")
    parser.add_argument("--limit", type=int, help="process at most N products")
    parser.add_argument("--product", type=int, help="process a single product id")
    parser.add_argument("--workers", type=int, default=8, help="parallel downloads (default 8)")
    parser.add_argument("--retry-flagged", action="store_true", help="reprocess products previously flagged")
    parser.add_argument("--source-url", help="store this image URL for --product, bypassing the search ladder")
    parser.add_argument("--no-verify", action="store_true", help="accept the first lookup hit without the model")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if args.status:
        return report()
    return run(limit=args.limit, product_id=args.product, workers=args.workers,
               retry_flagged=args.retry_flagged, verify_searched=not args.no_verify,
               source_url=args.source_url)


if __name__ == "__main__":
    raise SystemExit(main())
