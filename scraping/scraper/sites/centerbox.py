"""Centerbox Supermercados: two public sources.

* **Prices** - the online store (``www.conceito.lojacenterbox.com.br``, Centerbox's Conceito branch) is an
  Instabuy storefront whose product lists come from a JSON API (``api.ibecom.com.br``) that answers a plain
  GET given the store's own id in ``x-store-id``. That id is written into the store's home page, so it is
  read from there rather than hard-coded. ``/api_ecommerce/v5/offers`` is exactly the store's "Ofertas" page:
  the regular price, the promo price with its end date, and the club (CRM) price when there is one.
  (The older ``loja.centerbox.com.br`` storefront on the Mercadapp platform now only says "download the
  app" and loads no offers, so it is not used.)
* **Flyers** - ``www.grupocenterbox.com.br/ofertas`` lists "Ofertas da semana" (this week's pages, one image
  each: "... - Frente" / "... - Verso" are two sides of the same flyer) above an archive of "Ofertas
  anteriores". Only this week's are listed, as the same ``Encarte`` Cometa's flyers use, shown as images.
"""

import json
import logging
import re
import time
import zlib
from datetime import datetime
from html import unescape
from typing import Dict, List, Optional

from scraper.base import ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper
from scraper.sites.cometa import Encarte

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
PAUSE_SECONDS = 1.0  # between pages: the API rate-limits (429) a client that pages through its whole list at speed
_STORE_ID = re.compile(r'\\?"store\\?":\{\\?"id\\?":\\?"([0-9a-f]{24})')
_IMAGE_BASE = "https://assets.ibecom.com.br/ib.item.image.medium/m-"
_FLYER_ITEM = re.compile(
    r'<div class="offers__item">\s*<h3[^>]*>(.*?)</h3>\s*<img[^>]*src="([^"]+)"', re.DOTALL)
_SIDE = re.compile(r"\s*[–-]\s*(?:Frente|Verso|\d+)\s*$", re.IGNORECASE)
_FILE_DATE = re.compile(r"(20\d\d-\d\d-\d\d)")


class CenterboxScraper(BaseScraper):
    site_name = "Centerbox"
    site_key = "centerbox"
    base_url = "https://www.grupocenterbox.com.br"
    offers_url = "https://www.conceito.lojacenterbox.com.br/promocoes"
    store_url = "https://www.conceito.lojacenterbox.com.br"
    api_url = "https://api.ibecom.com.br/api_ecommerce/v5/offers"

    # ---- prices -----------------------------------------------------------------------------------------

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        store_id = self._store_id()
        self.session.headers.update({"x-store-id": store_id, "Origin": self.store_url, "Referer": self.store_url + "/"})
        products: List[ProductPrice] = []
        page = 1
        while len(products) < limit:
            payload = json.loads(self.fetch_raw(self.api_url, params={"page": page, "limit": PAGE_SIZE, "sort": "popular"}))
            items = payload.get("data") or []
            if not items:
                break
            products += [p for p in map(self._to_product_price, items) if p]
            page += 1
            time.sleep(PAUSE_SECONDS)
        logger.info("[%s] %d offer(s) read from %d page(s)", self.site_name, len(products), page - 1)
        return products[:limit]

    def _store_id(self) -> str:
        found = _STORE_ID.search(self.fetch_raw(self.store_url + "/"))
        if not found:
            raise RuntimeError("Centerbox: could not find the store id in the store's home page")
        return found.group(1)

    def _to_product_price(self, item: dict) -> Optional[ProductPrice]:
        config = item.get("price_config") or {}
        regular = config.get("price")
        if not regular or not (item.get("stock") or {}).get("has_available_stock", True):
            return None
        promo = (config.get("price_discount") or {}).get("promo_price")
        club = (config.get("promo_crm_massive") or {}).get("price")
        everyone = promo if promo and promo < regular else regular
        name = item["name"].strip()
        if item.get("unit_type") == "KG" and not re.search(r"\bkg\b", name, re.IGNORECASE):
            name += " Kg"  # a weighed item's price is per kilo, which the name has to say for the size parser
        price, regular_price, label = everyone, None, None
        if club and club < everyone:
            price, regular_price, label = club, everyone, "Clube CBOX"  # served as both a club and an everyone offer
        elif everyone < regular:
            regular_price, label = regular, f"{round((1 - everyone / regular) * 100)}% OFF"
        image = item.get("image")
        return ProductPrice(
            store_name=self.site_name, product_name=name, price=price,
            url=f"{self.store_url}/p/{item['slug']}", regular_price=regular_price, offer=label,
            brand=(item.get("brand") or "").strip() or None,
            image_url=_IMAGE_BASE + image if image else None,
        )

    # ---- flyers -----------------------------------------------------------------------------------------

    def fetch_encartes(self) -> List[Encarte]:
        """This week's flyers, in the order the site lists them."""
        return self.parse_flyers(self.fetch_raw(self.base_url + "/ofertas/"))

    @staticmethod
    def parse_flyers(page_html: str) -> List[Encarte]:
        week = page_html.split("Ofertas anteriores", 1)[0]  # the archive below is not this week's
        sides: Dict[str, List[str]] = {}
        for title, src in _FLYER_ITEM.findall(week):
            sides.setdefault(_SIDE.sub("", unescape(title).strip()), []).append(src)
        encartes = []
        for name, pages in sides.items():
            dates = [m.group(1) for m in (_FILE_DATE.search(p) for p in pages) if m]
            encartes.append(Encarte(
                id=zlib.crc32(name.encode("utf-8")), name=name, description="", cover_url=pages[0], pdf_url=None,
                pages=pages, posted_at=datetime.fromisoformat(max(dates)).isoformat() if dates else None,
            ))
        return encartes
