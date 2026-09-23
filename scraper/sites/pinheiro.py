"""Pinheiro Supermercado scraper.

The online store (a VipCommerce Angular app) lists its promotions at /ofertas; the old target, /produtos,
redirects to a "página não encontrada" page. The page is client-side rendered, so it is loaded with a
stealth browser.

The page shows only 20 offers and asks for the next 20 as it is scrolled, but the endpoint behind it
(``.../produtos/em-oferta?page=N``) holds all of them: 946 at the time of writing. That endpoint wants the
guest session the page creates for itself when it opens, so the scraper lets the page log itself in and then
reads the pages of that endpoint from inside the page, with the same session and headers the page uses.
Nothing is copied out of the site's scripts. If that yields nothing, it falls back to the 20 rendered cards.

Each API item carries the name, the shelf price (``oferta.preco_oferta``), the price before the offer
(``oferta.preco_antigo``), whether it can be bought now, and the offer's kind ("PinClube" for prices reserved
for the store's club members, "Leve e pague", or a price for buying several). Each card, in text, reads:

    [Oferta do Dia | PinClube]
    Refrigerante H2oh Limao 500ml Pet
    R$ 4,29 /un        <- price shown
    7% OFF
    R$ 4,59            <- regular price

The API does not say how many units the store has: ``quantidade_maxima`` is the most one order may hold,
so it is not recorded as stock.

The chain's real, physical branches (see :meth:`PinheiroScraper.fetch_locations`) come from a different
source: the "Nossas Lojas" institutional page the store's own CMS serves, read the same session-reusing way
as the offers, with each branch's name and address parsed out of its HTML.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from html import unescape

from bs4 import BeautifulSoup, Tag

from scraper.base import BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper

logger = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
_DISCOUNT_RE = re.compile(r"(\d+)\s*%\s*OFF", re.IGNORECASE)
_CLUB = "PinClube"

# Runs in the page once its offers have loaded. The endpoint, the store and the organisation are read from
# the request the page itself made, so nothing here is specific to one store's numbers.
_READ_OFFERS_JS = r"""
async () => {
  const cookie = (n) => (document.cookie.split('; ').find((c) => c.startsWith(n + '=')) || '').slice(n.length + 1);
  const seen = performance.getEntriesByType('resource').map((e) => e.name).find((n) => /\/produtos\/em-oferta\?/.test(n));
  if (!seen) return {error: 'the page did not ask for its offers', items: []};
  const url = new URL(seen);
  const headers = {
    Accept: 'application/json',
    Authorization: 'Bearer ' + cookie('vip-token'),
    'sessao-id': cookie('sessao-id'),
    DomainKey: location.hostname.replace(/^www\./, ''),
    OrganizationId: (url.pathname.match(/\/org\/(\d+)\//) || [])[1],
    FilialID: (url.pathname.match(/\/filial\/(\d+)\//) || [])[1],
  };
  const items = [];
  let pages = 1;
  for (let page = 1; page <= pages && page <= MAX_PAGES; page++) {
    url.searchParams.set('page', page);
    const res = await fetch(url, {headers});
    if (!res.ok) return {error: 'status ' + res.status + ' on page ' + page, items};
    const body = await res.json();
    items.push(...body.data);
    pages = body.paginator.total_pages;
    await new Promise((resolve) => setTimeout(resolve, PAUSE_MS));
  }
  return {error: null, items};
}
"""
MAX_PAGES = 100  # 20 offers each; the store has about 50 pages
PAUSE_MS = 120  # between pages, so the store's own service is not hammered

# Runs once the page has made at least one request of its own: that request's URL carries the organisation
# and store ids the API wants, the same way _READ_OFFERS_JS derives them. "Nossas Lojas" ("Our Stores") is
# one of the institutional pages the store's own CMS serves from this single endpoint.
_READ_LOJAS_JS = r"""
async () => {
  const cookie = (n) => (document.cookie.split('; ').find((c) => c.startsWith(n + '=')) || '').slice(n.length + 1);
  const seen = performance.getEntriesByType('resource').map((e) => e.name).find((n) => /\/org\/\d+\/filial\/\d+\//.test(n));
  if (!seen) return {error: 'no request to the store\'s API seen yet', html: null};
  const m = seen.match(/\/org\/(\d+)\/filial\/(\d+)\//);
  const headers = {
    Accept: 'application/json',
    Authorization: 'Bearer ' + cookie('vip-token'),
    'sessao-id': cookie('sessao-id'),
    DomainKey: location.hostname.replace(/^www\./, ''),
    OrganizationId: m[1],
    FilialID: m[2],
  };
  const res = await fetch('https://services.vipcommerce.com.br/ws/loja/paginas/index/1', {headers});
  if (!res.ok) return {error: 'status ' + res.status, html: null};
  const body = await res.json();
  const page = (body.paginas || []).find((p) => p.slug === 'nossas-lojas');
  return {error: page ? null : 'the "nossas-lojas" institutional page was not found', html: page ? page.conteudo : null};
}
"""
# Each branch reads "<h2>Pinheiro <name></h2> ... <strong>Endereço:</strong> <address>" in that CMS page's
# HTML (see fetch_locations); real, spot-checked example: "Pinheiro Aquiraz" / "Av. Nossa Sra. de Lurdes,
# 77 - Centro". Matched after unescaping the page's HTML entities (accents, "Endereço" itself included).
_BRANCH_RE = re.compile(
    r"<h2[^>]*>\s*Pinheiro\s+([^<]+?)\s*</h2>.*?Endereço:</strong>\s*([^<]+?)\s*</p>",
    re.IGNORECASE | re.DOTALL,
)


def _money(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _reais(value: float) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


class PinheiroScraper(BaseScraper):
    site_name = "Pinheiro Supermercado"
    site_key = "pinheiro"
    base_url = "https://www.lojaonline.pinheirosupermercado.com.br"
    offers_url = base_url + "/ofertas"

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        """Scrape the promotions (``query`` is ignored)."""
        logger.info("[%s] Starting scrape (limit=%d)", self.site_name, limit)
        read: Dict[str, Any] = {}
        try:
            soup = self.render(self.offers_url, wait_seconds=6, page_action=self._reader(read))
        finally:
            self.close()

        results = self.parse_api_offers(read.get("items") or [], limit=limit)
        if read.get("error"):
            # What was read is real, but the list may be short: a later scrape completes it.
            logger.warning("[%s] Offers API stopped early: %s (%d read)", self.site_name, read["error"], len(results))
        if results:
            logger.info("[%s] Offers API yielded %d products", self.site_name, len(results))
            return results

        logger.warning("[%s] Offers API gave nothing; reading the rendered cards (about 20)", self.site_name)
        results = self.parse_offers(soup, limit=limit)
        if not results:
            logger.warning("[%s] No product cards found; markup may have changed", self.site_name)
        return results

    @staticmethod
    def _reader(read: Dict[str, Any]):
        """A page action that leaves the API's items (and any error) in ``read``."""

        def action(page):
            try:
                page.wait_for_selector("div.vip-card-produto", timeout=30000)
                js = _READ_OFFERS_JS.replace("MAX_PAGES", str(MAX_PAGES)).replace("PAUSE_MS", str(PAUSE_MS))
                read.clear()
                read.update(page.evaluate(js) or {})
            except Exception as exc:  # Scrapling only logs an error raised here; keep what it was told
                read["error"] = str(exc)
            return page

        return action

    def fetch_locations(self) -> List[BranchLocation]:
        """The chain's real, physical branches: name and address, read from its own "Nossas Lojas" page."""
        read: Dict[str, Any] = {}
        try:
            self.render(self.base_url, wait_seconds=6, page_action=self._locations_reader(read))
        finally:
            self.close()
        if read.get("error"):
            logger.warning("[%s] Could not read the branch list: %s", self.site_name, read["error"])
        branches = self._parse_locations_html(read.get("html") or "")
        logger.info("[%s] %d real branch(es) found", self.site_name, len(branches))
        return branches

    @staticmethod
    def _locations_reader(read: Dict[str, Any]):
        """A page action that leaves the "Nossas Lojas" page's raw HTML (and any error) in ``read``."""

        def action(page):
            try:
                page.wait_for_timeout(4000)  # no fixed selector to wait for on this page; a plain pause
                read.clear()
                read.update(page.evaluate(_READ_LOJAS_JS) or {})
            except Exception as exc:  # Scrapling only logs an error raised here; keep what it was told
                read["error"] = str(exc)
            return page

        return action

    @staticmethod
    def _parse_locations_html(html: str) -> List[BranchLocation]:
        branches, seen = [], set()
        for name, address in _BRANCH_RE.findall(unescape(html)):
            name, address = name.strip(), address.strip()
            if not name or not address or name in seen:
                continue
            seen.add(name)
            branches.append(BranchLocation(external_id=name, name=name, address=address))
        return branches

    def parse_api_offers(self, items: List[Dict[str, Any]], limit: int = 1000) -> List[ProductPrice]:
        """Products from the offers endpoint's items; sold-out and repeated items are left out."""
        results: List[ProductPrice] = []
        seen = set()
        for item in items:
            if item.get("produto_id") in seen:
                continue
            seen.add(item.get("produto_id"))
            product = self._item_to_product(item)
            if product is not None:
                results.append(product)
                if len(results) >= limit:
                    break
        return results

    def _item_to_product(self, item: Dict[str, Any]) -> Optional[ProductPrice]:
        offer = item.get("oferta") or {}
        name, price = (item.get("descricao") or "").strip(), _money(offer.get("preco_oferta"))
        if not name or price is None or item.get("disponivel") is False:
            return None
        regular = _money(offer.get("preco_antigo"))
        # The store sometimes lists a price a centavo above the offer ("28,40" against "28,39"): not a discount.
        if regular is not None and round((1 - price / regular) * 100) < 1:
            regular = None
        return ProductPrice(
            store_name=self.site_name,
            product_name=name,
            price=price,
            url=f"{self.base_url}/produto/{item.get('produto_id')}/{item.get('link') or ''}".rstrip("/"),
            regular_price=regular,
            offer=self._label(offer, price, regular),
        )

    @staticmethod
    def _label(offer: Dict[str, Any], price: float, regular: Optional[float]) -> Optional[str]:
        """The deal in words: the discount, then who it is for, then any condition on the quantity."""
        parts = []
        if regular:
            parts.append(f"{round((1 - price / regular) * 100)}% OFF")
        if offer.get("nome") == _CLUB:
            parts.append(_CLUB)
        minimum, pay = offer.get("quantidade_minima") or 1, offer.get("quantidade_pagar") or 1
        if pay < minimum:
            parts.append(f"Leve {minimum} pague {pay}")
        for tier in offer.get("faixas_precos") or []:
            each, quantity = _money(tier.get("valor")), tier.get("quantidade")
            if each is not None and quantity and each < price:
                parts.append(f"{quantity} un por {_reais(each)} cada")
        return " · ".join(parts) or None

    def parse_offers(self, soup: BeautifulSoup, limit: int = 1000) -> List[ProductPrice]:
        """Products from the rendered cards (about 20): the fallback when the API is not reachable."""
        results: List[ProductPrice] = []
        seen = set()
        for card in soup.select("div.vip-card-produto"):
            link = card.select_one('a[href*="/produto/"]')
            if link is None or link["href"] in seen:
                continue
            seen.add(link["href"])
            product = self._parse_card(card, link["href"])
            if product is not None:
                results.append(product)
                if len(results) >= limit:
                    break
        return results

    def _parse_card(self, card: Tag, href: str) -> Optional[ProductPrice]:
        # Links on a card: an empty image link, one wrapping the price block, sometimes the brand
        # alone ("Ariel"), and the full name. The name is the longest text without a price.
        names = [a.get_text(strip=True) for a in card.select('a[href*="/produto/"]')]
        names = [n for n in names if n and "R$" not in n]
        prices = _PRICE_RE.findall(card.get_text(" ", strip=True))
        if not names or not prices:
            return None
        price = self._clean_price(prices[0])
        regular = self._clean_price(prices[1]) if len(prices) > 1 else None
        text = card.get_text(" ", strip=True)
        discount = _DISCOUNT_RE.search(text)
        label = f"{discount.group(1)}% OFF" if discount else None
        if _CLUB.lower() in text.lower():
            label = f"{label} · {_CLUB}" if label else _CLUB
        return ProductPrice(
            store_name=self.site_name,
            product_name=max(names, key=len),
            price=price,
            url=self._make_absolute(href),
            regular_price=regular if regular and regular > price else None,
            offer=label,
        )
