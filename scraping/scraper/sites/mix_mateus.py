"""Mix Mateus (Grupo Mateus's wholesale-retail format): its weekly flyers, the prices printed in them, and its branches.

The group's flyers site, ``ofertasmateus.com``, is a small PHP app that answers JSON through one same-origin
proxy, and needs no browser or login:

    /api-proxy.php?endpoint=/estados/CE/cidades
    /api-proxy.php?endpoint=/cidades/fortaleza/lojas
    /api-proxy.php?endpoint=/encartes/CE/fortaleza/<store id>?marca=MA     (MA is the Mix Mateus brand)
    /api-proxy.php?file=uploads/encartes/<file>.pdf

The flyers are the same for every Mix Mateus store in Ceará, and each carries its own start and end time. They
are PDFs with a real text layer (made by a flyer generator), so :meth:`scrape` reads the printed prices out of
them exactly, with :mod:`scraper.flyer_pdf`, instead of guessing at pixels as Cometa's flyers need. A flyer that
is a flat image (one of the brand flyers is) yields no offers but is still listed, shown as a PDF.

The branches come with a text address and no coordinates; those are geocoded afterward like the other chains'.
The group's other format, "Mateus Supermercados" (brand SM), has no store in Fortaleza and is left out.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from scraper import flyer_pdf
from scraper.base import DEFAULT_LIMIT, BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper
from scraper.sites.cometa import Encarte

logger = logging.getLogger(__name__)

FORTALEZA = ZoneInfo("America/Fortaleza")
_BRAND_PREFIX = "Mix Mateus "
_STAMP = "%Y-%m-%d %H:%M:%S"


class MixMateusScraper(BaseScraper):
    site_name = "Mix Mateus"
    site_key = "mixmateus"
    base_url = "https://ofertasmateus.com"
    offers_url = base_url
    state = "CE"
    brand = "MA"  # Mix Mateus; "SM" is Mateus Supermercados
    reference_city = "fortaleza"  # the flyers are the same in every city: this one's first store is asked for them

    def _api(self, endpoint: str):
        payload = json.loads(self.fetch_raw(f"{self.base_url}/api-proxy.php", params={"endpoint": endpoint}))
        if payload.get("status") != "success":
            raise RuntimeError(f"{endpoint} answered {payload.get('status')!r}")
        return payload.get("data") or []

    def _stores(self, city: str) -> List[dict]:
        return [s for s in self._api(f"/cidades/{city}/lojas") if s.get("marca") == self.brand and s.get("idloja")]

    # --- flyers ---------------------------------------------------------------------------------------------

    def file_url(self, path: str) -> str:
        return f"{self.base_url}/api-proxy.php?file={quote(path, safe='')}"

    def fetch_encartes(self, now: Optional[datetime] = None) -> List[Encarte]:
        """The flyers in force or about to start, with their PDF; the site keeps listing none that ended."""
        now = now or datetime.now(FORTALEZA).replace(tzinfo=None)
        stores = self._stores(self.reference_city)
        if not stores:
            raise RuntimeError(f"no {self.site_name} store in {self.reference_city}: cannot ask for its flyers")
        raw = self._api(f"/encartes/{self.state}/{self.reference_city}/{stores[0]['idloja']}?marca={self.brand}")
        encartes = []
        for item in raw:
            start, end = self._stamp(item.get("inicio")), self._stamp(item.get("validade"))
            if not item.get("arquivo") or not item.get("id_encarte") or (end is not None and end < now):
                continue
            url = self.file_url(item["arquivo"])
            encartes.append(Encarte(
                id=item["id_encarte"], name=(item.get("descricao") or "").strip() or "Encarte", description="",
                cover_url=url, pdf_url=url, pages=[],
                posted_at=start.isoformat() if start else None, valid_until=end.isoformat() if end else None,
            ))
        return encartes

    @staticmethod
    def _stamp(text: Optional[str]) -> Optional[datetime]:
        try:
            return datetime.strptime((text or "").strip(), _STAMP)
        except ValueError:
            return None

    # --- prices ---------------------------------------------------------------------------------------------

    def scrape(self, query: str = "", limit: int = DEFAULT_LIMIT) -> List[ProductPrice]:
        """The prices printed in each current flyer, the lowest where a product is in several."""
        encartes = self.fetch_encartes()
        logger.info("[%s] %d flyers published", self.site_name, len(encartes))
        best: Dict[str, ProductPrice] = {}
        for encarte in encartes:
            try:
                pdf = self._fetch_with_retry("get", encarte.pdf_url, timeout=self.timeout).content
                offers = flyer_pdf.read_offers(pdf)
            except ImportError:
                logger.warning("[%s] pdfplumber is not installed, so no prices are read from the flyers "
                               "(pip install -r requirements.txt)", self.site_name)
                return []
            except Exception as exc:
                logger.warning("[%s] Could not read flyer '%s': %s", self.site_name, encarte.name, exc)
                continue
            logger.info("[%s] %s: %d prices read", self.site_name, encarte.name, len(offers))
            until = self._stamp(encarte.valid_until.replace("T", " ")) if encarte.valid_until else None
            label = f"Encarte até {until:%d/%m}" if until else "Encarte"
            for offer in offers:
                key = offer.name.casefold()
                if key in best and best[key].price <= offer.price:
                    continue
                best[key] = ProductPrice(
                    store_name=self.site_name, product_name=offer.name, price=offer.price,
                    url=encarte.pdf_url, offer=label,
                )
        return list(best.values())[:limit]

    # --- branches -------------------------------------------------------------------------------------------

    def fetch_locations(self) -> List[BranchLocation]:
        try:
            cities = self._api(f"/estados/{self.state}/cidades")
        except Exception as exc:
            logger.warning("[%s] Could not fetch the branch list: %s", self.site_name, exc)
            return []
        branches, seen = [], set()
        for city in cities:
            try:
                stores = self._stores(city["idcidade"])
            except Exception as exc:
                logger.warning("[%s] Could not fetch the stores of %s: %s", self.site_name, city.get("idcidade"), exc)
                continue
            for store in stores:
                branch = self._to_branch(store, (city.get("descricao") or "").strip())
                if branch is not None and branch.external_id not in seen:
                    seen.add(branch.external_id)
                    branches.append(branch)
        logger.info("[%s] %d branch(es) found in %s", self.site_name, len(branches), self.state)
        return branches

    def _to_branch(self, store: dict, city: str) -> Optional[BranchLocation]:
        name = " ".join((store.get("nome_exibicao") or "").split()).removeprefix(_BRAND_PREFIX).strip()
        address = self._address(store.get("endereco") or "", city)
        if not name or not address:
            return None
        return BranchLocation(external_id=str(store["idloja"]), name=name, address=address)

    def _address(self, text: str, city: str) -> str:
        """A street address a geocoder can use: the site's free text is "Fortaleza-Ce/ Bairro: X - Av. Y, 2100."
        or "BR-116, 9800 - Messejana, Fortaleza - CE, 60821-000, Brasil"."""
        text = re.sub(r"^\s*[\wÀ-ÿ ]+\s*[-/]\s*CE\s*[/-]\s*", "", text, flags=re.IGNORECASE)  # "Fortaleza-Ce/ ", "Maranguape/CE - "
        text = re.sub(r"\([^)]*\)", " ", text)  # "(CE-065)"
        text = re.sub(r"\bBrasil\b|\bBairro:\s*", " ", text, flags=re.IGNORECASE)
        text = " ".join(text.replace("–", "-").split()).strip(" .,-")
        text = re.sub(r"[\s,]*,[\s,]*", ", ", text)
        if not text:
            return ""
        if re.match(r"(BR|CE)-\d+", text):  # a highway address: the geocoder finds it without the postcode, not with it
            text = re.sub(r",?\s*\b\d{5}-?\d{3}\b", "", text)
        if re.search(rf"\b{self.state}\b", text):
            return text  # already says the state, wherever it is
        if city and city.casefold() in text.casefold():
            return f"{text}, {self.state}"
        return f"{text}, {city}, {self.state}" if city else f"{text}, {self.state}"
