"""Cometa Supermercados scraper.

Cometa publishes its offers as flyers ("encartes") shown as a carousel of
banner images on /encartes. The page is a Next.js app that fills the carousel
from a public JSON endpoint, so we call that instead of rendering the page:

    GET /api/encartes  ->  {"data": [{"name", "description", "cover", "pdf"}, ...]}

``cover`` and ``pdf`` hold *relative* upload paths (``/uploads/...``). Those do
not exist on the shop domain (it answers with an HTML 404 page); the site's own
client prefixes them with the CMS host, which is what :meth:`media_url` does.

The flyers are flat images (the PDFs have no text layer), so :meth:`scrape`
reads them with OCR (see :mod:`scraper.flyer_ocr`), keeping only offers whose
prices agree with the flyer's own discount badge. OCR needs the optional
``easyocr`` package; without it :meth:`scrape` returns no products and
:meth:`fetch_encartes` still lists the flyers.

The chain's real, physical branches (see :meth:`fetch_locations`) come from a third endpoint, the "Onde
Estamos" ("Where We Are") page's own API, ``GET /api/onde-estamos``: each branch already carries its own
real coordinates, so unlike the other chains this one needs no geocoding - and no session or guest token
either, a plain request answers it.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from scraper import flyer_ocr
from scraper.base import BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper

logger = logging.getLogger(__name__)


@dataclass
class Encarte:
    """One published flyer."""
    id: int
    name: str
    description: str  # includes the validity window, e.g. "Ofertas válidas de 20 a 22/09 ..."
    cover_url: str    # banner image, full size, absolute URL
    pdf_url: Optional[str]


class CometaScraper(BaseScraper):
    site_name = "Cometa"
    site_key = "cometa"
    base_url = "https://cometasupermercados.com.br"
    offers_url = base_url + "/encartes"
    api_url = base_url + "/api/encartes"
    media_base_url = "https://adminx.cometasupermercados.com.br"

    def media_url(self, path: str) -> str:
        """Resolve an upload path from the API to an absolute URL on the CMS host."""
        if path.startswith(("http://", "https://")):
            return path
        return self.media_base_url + "/" + path.lstrip("/")

    def fetch_encartes(self) -> List[Encarte]:
        """Return the currently published flyers, newest first."""
        payload = json.loads(self.fetch_raw(self.api_url))
        encartes = []
        for item in payload.get("data", []):
            cover = (item.get("cover") or {}).get("url")
            if not cover:
                continue
            pdf = (item.get("pdf") or {}).get("url")
            encartes.append(
                Encarte(
                    id=item["id"],
                    name=(item.get("name") or "").strip(),
                    description=(item.get("description") or "").strip(),
                    cover_url=self.media_url(cover),
                    pdf_url=self.media_url(pdf) if pdf else None,
                )
            )
        return encartes

    def fetch_locations(self) -> List[BranchLocation]:
        """The chain's real, physical branches, with real coordinates: its own public "Onde Estamos" API.

        Unlike the other chains' sources, this one needs no session or guest token - a plain GET answers it.
        """
        branches, seen, page, pages = [], set(), 1, 1
        while page <= pages:
            try:
                payload = json.loads(self.fetch_raw(
                    self.base_url + "/api/onde-estamos",
                    params={"pagination[page]": page, "pagination[pageSize]": 100},
                ))
            except Exception as exc:
                logger.warning("[%s] Could not fetch the branch list: %s", self.site_name, exc)
                break
            for item in payload.get("data") or []:
                branch = self._to_branch(item)
                if branch is not None and branch.external_id not in seen:
                    seen.add(branch.external_id)
                    branches.append(branch)
            pages = ((payload.get("meta") or {}).get("pagination") or {}).get("pageCount") or 1
            page += 1
        logger.info("[%s] %d real branch(es) found", self.site_name, len(branches))
        return branches

    @staticmethod
    def _to_branch(item: dict) -> Optional[BranchLocation]:
        branch_id = item.get("id")
        name, address = (item.get("name") or "").strip(), (item.get("address") or "").strip()
        parts = str(item.get("coordinates") or "").split(",")
        if branch_id is None or not name or not address or len(parts) != 2:
            return None
        try:
            lat, lon = float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            return None
        # Every branch is named "Loja <place>" ("Loja Aldeota"); the chain's own name is shown separately.
        return BranchLocation(external_id=str(branch_id), name=name.removeprefix("Loja ").strip() or name,
                              address=address, lat=lat, lon=lon)

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        """OCR every flyer and return the offers whose prices check out.

        Flyers without discount badges (price tags only) yield nothing, since
        their OCR'd prices cannot be verified; see :mod:`scraper.flyer_ocr`.
        """
        encartes = self.fetch_encartes()
        logger.info("[%s] %d encartes published", self.site_name, len(encartes))
        if not flyer_ocr.ocr_available():
            logger.warning(
                "[%s] easyocr is not installed, so no products are read from the flyers "
                "(pip install -r requirements-ocr.txt)", self.site_name,
            )
            return []

        best = {}  # the same product often appears in several flyers; keep the lowest price
        for encarte in encartes:
            try:
                image = self._fetch_with_retry("get", encarte.cover_url, timeout=self.timeout).content
                offers = flyer_ocr.read_offers(image)
            except Exception as exc:
                logger.warning("[%s] Could not read flyer '%s': %s", self.site_name, encarte.name, exc)
                continue
            logger.info("[%s] %s: %d verified offers", self.site_name, encarte.name, len(offers))
            for offer in offers:
                key = offer.name.casefold()
                if key in best and best[key].price <= offer.price:
                    continue
                best[key] = ProductPrice(
                    store_name=self.site_name,
                    product_name=offer.name,
                    price=offer.price,
                    url=encarte.cover_url,
                    regular_price=offer.regular_price,
                    offer=f"{offer.discount_pct}% de desconto",
                )
        return list(best.values())[:limit]
