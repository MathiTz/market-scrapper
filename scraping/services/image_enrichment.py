"""Fill in product images for sources that do not ship one.

Background
----------
VTEX-backed stores (see ``scraper/vtex.py``) already return ``imageUrl`` per SKU, so
their products arrive with ``Product.image_url`` populated. Flyer/OCR and plain-HTML
sources do not, and ``_get_or_create_product`` is deliberately write-once: it will
never overwrite an existing image, but it also never goes looking for a missing one.
The result is a long tail of products with ``image_url IS NULL``.

This module closes that tail. It works in two stages, cheapest first:

1. ``resolve_by_gtin`` - if we know the product's GTIN/EAN, ask Open Food Facts
   (free, no key, no scraping) for the canonical photo. This is the highest quality
   match because it is keyed on the barcode, not on the name.
2. ``resolve_by_search`` - otherwise fall back to a name search against the same
   public API, accepting a hit only when the returned name is a close enough match
   (``min_name_similarity``) to avoid attaching a stranger's photo to our product.

Both stages are pure HTTP + JSON; nothing here drives a browser. Failures are
swallowed and reported per-product so one bad lookup never aborts a backfill run.

The service never writes an image over a non-empty one - callers can run it
repeatedly and it stays idempotent.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable, Optional

import requests
from sqlalchemy.orm import Session

from models import Product

logger = logging.getLogger(__name__)

# Open Food Facts: free, no API key, and it accepts a custom User-Agent for
# identification. Their docs ask for a descriptive UA and modest request rates.
DEFAULT_USER_AGENT = "market-scrapper/1.0 (product image backfill)"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MIN_SIMILARITY = 0.62

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ImageMatch:
    """A candidate image for a product, with the evidence behind it."""

    image_url: str
    source: str  # "gtin" | "search"
    confidence: float
    matched_name: Optional[str] = None


@dataclass
class EnrichmentResult:
    """Outcome of trying to give one product an image."""

    product_id: int
    name: str
    updated: bool
    image_url: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "updated": self.updated,
            "image_url": self.image_url,
            "source": self.source,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


def _normalize(text: Optional[str]) -> str:
    """Lowercase, strip punctuation/accents-ish, collapse whitespace for comparison."""
    if not text:
        return ""
    return " ".join(_WORD_RE.findall(text.lower()))


def name_similarity(a: Optional[str], b: Optional[str]) -> float:
    """Token-overlap-aware similarity in [0, 1].

    Plain ``SequenceMatcher`` punishes reordered words ("Leite Ninho 380g" vs
    "Ninho Leite 380g"), which is common between our titles and OFF's. We take the
    better of the raw ratio and a token-set ratio so word order matters less.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    raw = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return raw
    token = 2 * len(ta & tb) / (len(ta) + len(tb))
    return max(raw, token)


def _extract_image_url(payload: dict) -> Optional[str]:
    """Pull the best available image URL out of an OFF product payload."""
    for key in ("image_front_url", "image_url", "image_front_small_url"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


class ProductImageEnricher:
    """Resolve missing product images from public product databases."""

    BASE_URL = "https://world.openfoodfacts.org"

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float = DEFAULT_TIMEOUT,
        min_name_similarity: float = DEFAULT_MIN_SIMILARITY,
        request_delay: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = session or requests.Session()
        self.http.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        self.timeout = timeout
        self.min_name_similarity = min_name_similarity
        self.request_delay = request_delay
        self._sleep = sleep

    # -- low level lookups -------------------------------------------------

    def _get_json(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.BASE_URL}{path}"
        try:
            resp = self.http.get(url, params=params, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - a lookup failure must never abort a run
            logger.debug("image lookup failed for %s: %s", url, exc)
            return None
        if self.request_delay:
            self._sleep(self.request_delay)
        if resp.status_code != 200:
            logger.debug("image lookup %s -> HTTP %s", url, resp.status_code)
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def resolve_by_gtin(self, gtin: Optional[str]) -> Optional[ImageMatch]:
        """Barcode lookup - exact and therefore trusted at full confidence."""
        gtin = (gtin or "").strip()
        if not gtin.isdigit():
            return None
        payload = self._get_json(f"/api/v2/product/{gtin}.json")
        if not payload or payload.get("status") != 1:
            return None
        product = payload.get("product") or {}
        image_url = _extract_image_url(product)
        if not image_url:
            return None
        return ImageMatch(
            image_url=image_url,
            source="gtin",
            confidence=1.0,
            matched_name=product.get("product_name"),
        )

    def resolve_by_search(
        self, name: str, brand: Optional[str] = None
    ) -> Optional[ImageMatch]:
        """Name search - accepted only if the candidate clears the similarity bar."""
        query = " ".join(part for part in (brand, name) if part).strip()
        if not query:
            return None
        payload = self._get_json(
            "/cgi/search.pl",
            params={
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 10,
                "fields": "code,product_name,brands,image_front_url,image_url",
            },
        )
        if not payload:
            return None

        best: Optional[ImageMatch] = None
        for candidate in payload.get("products", []) or []:
            image_url = _extract_image_url(candidate)
            if not image_url:
                continue
            candidate_name = candidate.get("product_name") or ""
            score = name_similarity(name, candidate_name)
            if brand and candidate.get("brands"):
                score = max(score, name_similarity(brand, candidate.get("brands")))
            if score < self.min_name_similarity:
                continue
            if best is None or score > best.confidence:
                best = ImageMatch(
                    image_url=image_url,
                    source="search",
                    confidence=score,
                    matched_name=candidate_name,
                )
        return best

    # -- per product -------------------------------------------------------

    def resolve(self, product: Product) -> Optional[ImageMatch]:
        """Best image we can find for ``product``, GTIN first then name search."""
        match = self.resolve_by_gtin(getattr(product, "gtin", None))
        if match:
            return match
        return self.resolve_by_search(product.name, getattr(product, "brand", None))

    def enrich_product(self, db: Session, product: Product) -> EnrichmentResult:
        """Try to fill one product's image. Never overwrites an existing one."""
        if product.image_url:
            return EnrichmentResult(
                product_id=product.id,
                name=product.name,
                updated=False,
                image_url=product.image_url,
                reason="already has an image",
            )
        match = self.resolve(product)
        if not match:
            return EnrichmentResult(
                product_id=product.id,
                name=product.name,
                updated=False,
                reason="no match found",
            )
        product.image_url = match.image_url
        db.add(product)
        return EnrichmentResult(
            product_id=product.id,
            name=product.name,
            updated=True,
            image_url=match.image_url,
            source=match.source,
            confidence=match.confidence,
        )

    # -- batch -------------------------------------------------------------

    def enrich_missing(
        self,
        db: Session,
        limit: Optional[int] = None,
        only_ids: Optional[Iterable[int]] = None,
        commit_every: int = 25,
    ) -> list[EnrichmentResult]:
        """Backfill every product with no image, committing as we go.

        Committing in batches means a crash halfway through still leaves the
        images found so far, and a re-run simply skips them.
        """
        query = db.query(Product).filter(
            (Product.image_url.is_(None)) | (Product.image_url == "")
        )
        if only_ids is not None:
            ids = list(only_ids)
            if not ids:
                return []
            query = query.filter(Product.id.in_(ids))
        query = query.order_by(Product.id)
        if limit:
            query = query.limit(limit)

        results: list[EnrichmentResult] = []
        for index, product in enumerate(query.all(), start=1):
            results.append(self.enrich_product(db, product))
            if commit_every and index % commit_every == 0:
                db.commit()
        db.commit()
        return results


def enrich_missing_images(
    limit: Optional[int] = None,
    only_ids: Optional[Iterable[int]] = None,
    min_name_similarity: float = DEFAULT_MIN_SIMILARITY,
    request_delay: float = 0.0,
) -> dict:
    """Convenience entry point: open a session, backfill, return a summary dict."""
    from models import SessionLocal

    enricher = ProductImageEnricher(
        min_name_similarity=min_name_similarity, request_delay=request_delay
    )
    db = SessionLocal()
    try:
        results = enricher.enrich_missing(db, limit=limit, only_ids=only_ids)
    finally:
        db.close()
    updated = [r for r in results if r.updated]
    return {
        "checked": len(results),
        "updated": len(updated),
        "by_source": {
            source: sum(1 for r in updated if r.source == source)
            for source in ("gtin", "search")
        },
        "results": [r.as_dict() for r in results],
    }
