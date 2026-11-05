"""Assaí Atacadista: its weekly flyers and its branches. The site shows no product prices, so :meth:`scrape`
returns nothing and the flyers are shown as images, like Frangolândia's and Centerbox's.

The site (Drupal) sits behind Imperva's JavaScript challenge: a plain request gets a 403 "Pardon Our
Interruption" page, a stealth browser gets through. Both sources below are therefore read with
:meth:`render`, which uses Scrapling's StealthyFetcher.

* Flyers: ``/sites/default/files/static/ofertas_assai.json`` is what the offers page itself loads. It holds
  every current flyer with its page images, its validity dates and the stores it applies to (``lojas``,
  ids of ``nid``/``eid``), and a store list with each store's offers URL. The file is cached by the CDN
  unless the URL carries a changing query string, which the site's own script adds too.
* Branches: the "Nossas lojas" page embeds all 313 stores as JSON (``Drupal.settings.assai.lojas``) with
  address and coordinates, so no geocoding is needed.

Both are limited to one state (``state``, Ceará): the chain has stores in every state.
"""

import json
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

from scraper.base import DEFAULT_LIMIT, BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper
from scraper.sites.cometa import Encarte

logger = logging.getLogger(__name__)

_STORES_MARKER = '"assai":{"lojas":'
_BRAND = "Assaí "  # every store is named "Assaí <place>"; the chain's own name is shown separately
_FLYER_TITLE = "Jornal de Ofertas"


class AssaiScraper(BaseScraper):
    site_name = "Assaí Atacadista"
    site_key = "assai"
    base_url = "https://www.assai.com.br"
    offers_url = base_url + "/ofertas"
    flyers_url = base_url + "/sites/default/files/static/ofertas_assai.json"
    stores_url = base_url + "/nossas-lojas"
    state = "CE"
    state_slug = "ceara"  # how the flyers JSON names the state in a store's offers URL
    # The state's rough bounds (south, north, west, east): the site has put a store at another state's
    # coordinates (Iguatu at Campo Grande's), so a point outside is dropped and the address geocoded instead.
    bounds = (-7.9, -2.7, -41.5, -37.2)

    def scrape(self, query: str = "", limit: int = DEFAULT_LIMIT) -> List[ProductPrice]:
        return []  # flyers and branches only: the site publishes no prices

    # --- the two pages --------------------------------------------------------------------------------------

    def _flyers_json(self) -> dict:
        soup = self.render(f"{self.flyers_url}?v={time.time_ns()}", wait_seconds=1)
        pre = soup.find("pre")  # the browser wraps a JSON response in <pre>
        try:
            return json.loads(pre.get_text() if pre else soup.get_text())
        except ValueError:
            # From a datacenter address Imperva never lets the browser through: it answers 200 with its challenge page
            raise RuntimeError(
                f"{self.flyers_url} did not answer with JSON but with a page of {len(str(soup))} characters "
                "(Imperva's challenge?); set PROXY_ASSAI to a Brazilian residential or small-host exit") from None

    @staticmethod
    def parse_stores(page_html: str) -> List[dict]:
        """The store list embedded in the "Nossas lojas" page, or [] when the page has none (a challenge page)."""
        start = page_html.find(_STORES_MARKER)
        if start < 0:
            return []
        try:
            stores, _ = json.JSONDecoder().raw_decode(page_html[start + len(_STORES_MARKER):])
        except ValueError:
            return []
        return stores if isinstance(stores, list) else []

    # --- branches -------------------------------------------------------------------------------------------

    def fetch_locations(self) -> List[BranchLocation]:
        try:
            stores = self.parse_stores(str(self.render(self.stores_url, wait_seconds=2)))
        except Exception as exc:
            logger.warning("[%s] Could not fetch the branch list: %s", self.site_name, exc)
            return []
        branches, seen = [], set()
        for store in stores:
            if store.get("uf") != self.state:
                continue
            branch = self._to_branch(store)
            if branch is not None and branch.external_id not in seen:
                seen.add(branch.external_id)
                branches.append(branch)
        if not stores:
            logger.warning("[%s] The stores page held no store list", self.site_name)
        logger.info("[%s] %d real branch(es) found in %s", self.site_name, len(branches), self.state)
        return branches

    def _to_branch(self, store: dict) -> Optional[BranchLocation]:
        name = " ".join((store.get("n") or "").split())
        try:
            lat, lon = float(store["lat"]), float(store["lon"])
        except (KeyError, TypeError, ValueError):
            lat = lon = None  # no point at all: the address will be geocoded
        street = (store.get("logradouro") or "").strip(" ,")
        parts = [street, (store.get("complemento") or "").strip(" ,"), (store.get("c") or "").strip(), store.get("uf")]
        address = ", ".join(p for p in parts if p)
        if not name or not street or not store.get("loja_id"):
            return None
        south, north, west, east = self.bounds
        if lat is not None and not (south <= lat <= north and west <= lon <= east):
            logger.warning("[%s] %s: coordinates (%s, %s) are outside %s; the address will be geocoded",
                           self.site_name, name, lat, lon, self.state)
            lat = lon = None
        return BranchLocation(external_id=str(store["loja_id"]), name=name.removeprefix(_BRAND).strip() or name,
                              address=address, lat=lat, lon=lon)

    # --- flyers ---------------------------------------------------------------------------------------------

    def fetch_encartes(self, now: Optional[datetime] = None) -> List[Encarte]:
        """The flyers in force (or about to be) for the state's stores, each saying which stores it covers."""
        today = (now or datetime.now()).date()
        data = self._flyers_json()
        names = self._state_stores(data)
        if not names:
            raise RuntimeError(f"the flyers file lists no store under /ofertas/{self.state_slug}")
        encartes = []
        for flyer in data.get("ofertas") or []:
            covered = {s["nid"] for s in flyer.get("lojas") or [] if s.get("nid") in names}
            pages = [i["url"] for i in flyer.get("images") or [] if i.get("url")]
            if not covered or not pages:
                continue
            start, end = self._day(flyer.get("start_date")), self._day(flyer.get("end_date"))
            if end is not None and end < today:
                continue  # the file keeps a flyer until the chain removes it
            encartes.append(Encarte(
                id=flyer["id_oferta"], name=(flyer.get("title") or "").strip() or _FLYER_TITLE,
                description=self._scope(covered, names), cover_url=pages[0], pdf_url=None, pages=pages,
                posted_at=f"{start.isoformat()}T00:00:00" if start else None,
                valid_until=f"{end.isoformat()}T23:59:59" if end else None,
            ))
        return encartes

    def _state_stores(self, data: dict) -> Dict[int, str]:
        """``{store id: name}`` of the state's stores, from the offers URLs the flyers file lists them under."""
        prefix = f"/ofertas/{self.state_slug}/"
        return {int(s["nid"]): " ".join((s.get("name") or "").split()).removeprefix(_BRAND)
                for s in data.get("lojas") or [] if (s.get("url") or "").startswith(prefix) and s.get("nid")}

    @staticmethod
    def _scope(covered: Set[int], names: Dict[int, str]) -> str:
        """Who the flyer is for: every store, all but a few, or just a few."""
        if covered >= set(names):
            return "Todas as lojas do Ceará"
        left_out = sorted(names[n] for n in names if n not in covered)
        if len(left_out) < len(covered):
            return "Todas as lojas do Ceará, exceto: " + ", ".join(left_out)
        return "Lojas: " + ", ".join(sorted(names[n] for n in covered))

    @staticmethod
    def _day(text: Optional[str]):
        """A ``dd/mm/yyyy`` date, or None."""
        match = re.fullmatch(r"\s*(\d{2})/(\d{2})/(\d{4})\s*", text or "")
        if not match:
            return None
        try:
            return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1))).date()
        except ValueError:
            return None
