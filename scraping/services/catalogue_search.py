"""Search the whole catalogue - not only the products in the published snapshot.

``GET /api/search?q=arroz`` answers the products (any chain, listed right now) whose name or brand starts with each
typed word, in any order, ignoring accents and case - the same rule as the web app's own search (``lib/search.ts``),
so a word it finds in the snapshot is found here too. The Worker answers it from the cloud database's ``products``
and ``current_prices`` (api/src/store.ts); this module answers the same shape from the local database, for the
Flask API used in development.

    {"results": [{"key", "name", "brand", "category", "subcategory", "amount", "unit", "pack_count", "gtin",
                  "image_url", "prices": [{"store", "price_cents", "regular_price_cents", "deal_label",
                                           "source_url", "observed_at", "stock"}]}],
     "truncated": bool}
"""

import re
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import Product, Store
from services.price_points import product_key
from services.public_api import (
    _iso_utc, categorize, clean, display_name, latest_listed_prices, parse_size, subcategorize,
)

MIN_QUERY = 2
MAX_QUERY = 60
MAX_WORDS = 6
DEFAULT_LIMIT = 40
MAX_LIMIT = 60


def words_of(query: str) -> List[str]:
    """The typed words, lower-case and accent-free, letters and digits only; empty when the query is unusable."""
    text = clean(query or "")
    if not MIN_QUERY <= len(text) <= MAX_QUERY:
        return []
    return re.findall(r"[a-z0-9]+", text)[:MAX_WORDS]


def matches(text: str, words: List[str]) -> bool:
    own = re.findall(r"[a-z0-9]+", clean(text))
    return all(any(w.startswith(word) for w in own) for word in words)


def search(db: Session, query: str, limit: int = DEFAULT_LIMIT) -> Optional[dict]:
    """The matching products with every chain's current price, best matches first; None for an unusable query."""
    words = words_of(query)
    if not words:
        return None
    limit = max(1, min(limit, MAX_LIMIT))
    canonical: Dict[str, Store] = {}
    for store in db.query(Store).order_by(Store.id).all():
        canonical.setdefault(store.name, store)
    retailer_of = {s.id: canonical[s.name] for s in db.query(Store).all()}
    products = {p.id: p for p in db.query(Product).all()}

    found: Dict[str, dict] = {}
    for (product_id, retailer_id), price in latest_listed_prices(db, retailer_of).items():
        product = products.get(product_id)
        if product is None or not price.price or price.price <= 0:
            continue
        if not matches(f"{product.name} {product.brand or ''}", words):
            continue
        key = product_key(product.name)
        amount, unit, pack = parse_size(product.name)
        item = found.setdefault(key, {
            "key": key, "name": display_name(product.name), "brand": product.brand or "",
            "category": product.category or categorize(product.name), "subcategory": subcategorize(product.name),
            "amount": amount, "unit": unit, "pack_count": pack, "gtin": product.gtin,
            "image_url": product.image_url, "prices": [],
        })
        item["gtin"] = item["gtin"] or product.gtin
        item["image_url"] = item["image_url"] or product.image_url
        chain = canonical[retailer_of[price.store_id].name].name
        item["prices"] = [p for p in item["prices"] if p["store"] != chain] + [{
            "store": chain, "price_cents": round(price.price * 100),
            "regular_price_cents": round(price.regular_price * 100) if price.regular_price and price.regular_price > price.price else None,
            "deal_label": price.offer or None, "source_url": price.url or None,
            "observed_at": _iso_utc(price.scraped_at),
            "stock": price.stock,
        }]

    first = words[0]
    ranked = sorted(
        found.values(),
        key=lambda item: (0 if clean(item["name"]).startswith(first) else 1, len(item["name"]), item["name"]),
    )
    return {"results": ranked[:limit], "truncated": len(ranked) > limit}
