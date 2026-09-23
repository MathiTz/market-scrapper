"""Shared scraper for stores built on VTEX.

VTEX stores expose a public JSON product search, so no browser is needed:

    GET /api/io/_v/api/intelligent-search/product_search/category-1/<slug>
        ?count=50&page=N[&sort=discount:desc]

Each product carries ``items[0].sellers[0].commertialOffer`` with ``Price``
(what you pay), ``ListPrice`` (before any discount) and ``AvailableQuantity``.

Two modes, chosen per store with ``only_discounted``:

* True: read each category sorted by discount and stop at the first product
  without one, so only real offers are collected (Sam's Club);
* False: take the first products of each category at their current price, for
  stores that mostly sell at everyday prices (Atacadão has no promotions).

Subclasses set ``site_name``, ``site_key``, ``base_url`` and ``categories``.
"""

import json
import logging
from typing import List, Optional, Tuple

from scraper.base import BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper

logger = logging.getLogger(__name__)


def _clean_field(value: Optional[str]) -> Optional[str]:
    """A free-text field VTEX sometimes sends as `""`/`null`/whitespace instead of omitting outright."""
    text = (value or "").strip()
    return text or None


def _ean(value: Optional[str]) -> Optional[str]:
    """A real-looking GTIN/EAN (8, 12, 13 or 14 digits - matches the UI's own gtin validation), or None.

    A generic placeholder like "0" or "SEM EAN" is not a barcode; keeping it would look like real evidence
    for a product that has none.
    """
    text = (value or "").strip()
    return text if len(text) in (8, 12, 13, 14) and text.isdigit() and text != "0" * len(text) else None


def _image_url(images: Optional[list]) -> Optional[str]:
    """The first photo VTEX offers for this SKU, or None."""
    if not images:
        return None
    return _clean_field(images[0].get("imageUrl"))


# VTEX answers 10000 (or 99999) as the quantity when a store does not really track its stock, so
# anything from there up says nothing and is not kept.
UNTRACKED_STOCK = 10000

# Fortaleza's centre: real branches are returned ranked by distance from here, with their own coordinates,
# so nothing needs geocoding afterward (unlike scraper/mercadapp.py's branch list, which gives only text
# addresses). Each store's own pickup-point catalogue already seems metro-scoped (Atacadão and Sam's Club
# both came back with just their real Fortaleza-area branches, not every branch nationwide), so no radius
# is passed; if a chain's catalogue ever includes far-away branches this may need a distance cutoff.
_LOCATIONS_CENTER = "-38.5267;-3.7319"


class VtexScraper(BaseScraper):
    page_size = 50
    only_discounted = True
    categories: Tuple[str, ...] = ()

    @property
    def search_url(self) -> str:
        return self.base_url + "/api/io/_v/api/intelligent-search/product_search"

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        """Collect products from each category (``query`` is ignored)."""
        per_category = max(1, limit // len(self.categories))
        results: List[ProductPrice] = []
        seen = set()
        last_error: Optional[Exception] = None
        for slug in self.categories:
            try:
                offers = self._category_offers(slug, per_category)
            except Exception as exc:
                logger.warning("[%s] Category %s failed: %s", self.site_name, slug, exc)
                last_error = exc
                continue
            logger.info("[%s] %s: %d products", self.site_name, slug, len(offers))
            for offer in offers:
                if offer.url not in seen:
                    seen.add(offer.url)
                    results.append(offer)
        if not results and last_error is not None:
            raise last_error
        return results[:limit]

    def _category_offers(self, slug: str, cap: int) -> List[ProductPrice]:
        offers: List[ProductPrice] = []
        page = 1
        params = {"count": self.page_size}
        if self.only_discounted:
            params["sort"] = "discount:desc"
        while len(offers) < cap:
            payload = json.loads(self.fetch_raw(
                f"{self.search_url}/category-1/{slug}", params={**params, "page": page},
            ))
            products = payload.get("products") or []
            if not products:
                break
            for product in products:
                price, list_price, quantity = self._commercial_offer(product)
                if self.only_discounted and not list_price > price > 0:
                    return offers  # sorted by discount: everything after this has none
                if quantity > 0 and price > 0:
                    offers.append(self._to_product_price(product, price, list_price, quantity))
            if len(products) < self.page_size:
                break  # a short page is the last one
            page += 1
        return offers[:cap]

    @staticmethod
    def _commercial_offer(product: dict) -> Tuple[float, float, int]:
        item = (product.get("items") or [{}])[0]
        seller = (item.get("sellers") or [{}])[0]
        offer = seller.get("commertialOffer") or {}
        return (
            float(offer.get("Price") or 0),
            float(offer.get("ListPrice") or 0),
            int(offer.get("AvailableQuantity") or 0),
        )

    def fetch_locations(self) -> List[BranchLocation]:
        """The chain's real, physical branches, with their real coordinates: VTEX's own pickup-points API."""
        try:
            payload = json.loads(self.fetch_raw(
                self.base_url + "/api/checkout/pub/pickup-points",
                params={"geoCoordinates": _LOCATIONS_CENTER, "countryCode": "BRA"},
            ))
        except Exception as exc:
            logger.warning("[%s] Could not fetch the branch list: %s", self.site_name, exc)
            return []
        branches, seen = [], set()
        for entry in payload.get("items") or []:
            point = entry.get("pickupPoint") or {}
            address = point.get("address") or {}
            branch_id, coords = point.get("id"), address.get("geoCoordinates")
            name = (point.get("friendlyName") or "").strip()
            if (
                not branch_id or branch_id in seen or not point.get("isActive") or not name
                or not isinstance(coords, list) or len(coords) != 2
            ):
                continue
            street, number = address.get("street"), address.get("number")
            label = ", ".join(str(part).strip() for part in (
                f"{street} {number}".strip() if street else None,
                address.get("neighborhood"), address.get("city"), address.get("state"),
            ) if part and str(part).strip())
            if not label:
                continue
            seen.add(branch_id)
            branches.append(BranchLocation(external_id=str(branch_id), name=name, address=label, lon=coords[0], lat=coords[1]))
        logger.info("[%s] %d real branch(es) found", self.site_name, len(branches))
        return branches

    def _to_product_price(self, product: dict, price: float, list_price: float, quantity: int) -> ProductPrice:
        discounted = list_price > price
        item = (product.get("items") or [{}])[0]
        return ProductPrice(
            store_name=self.site_name,
            product_name=product["productName"].strip(),
            price=price,
            url=self._make_absolute(product.get("link") or ""),
            regular_price=list_price if discounted else None,
            offer=f"{round((1 - price / list_price) * 100)}% OFF" if discounted else None,
            stock=quantity if quantity < UNTRACKED_STOCK else None,
            brand=_clean_field(product.get("brand")),
            gtin=_ean(item.get("ean")),
            image_url=_image_url(item.get("images")),
        )
