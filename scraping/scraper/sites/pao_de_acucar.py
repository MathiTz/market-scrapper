"""Pão de Açúcar scraper.

The offers live on the home page, inside lazy-loaded carousels ("Semana nova,
ofertas imperdíveis", "Açougue completo", ...). The site is a Next.js app
behind a bot check (plain HTTP gets a "Verificação de segurança" page), so we
render it with a stealth browser and scroll to trigger the lazy sections.

Class names are styled-components hashes that change between deploys, so cards
are located by their ``/produto/<id>/<slug>`` link and parsed from text:

    Margarina Cremosa com Sal Qualy Pote 500g
    R$9,99                     <- regular price (struck through)
    25% OFF                    <- deal label
    A unid. sai por R$7,49     <- price with the deal applied

The chain's real, physical branches (see :meth:`fetch_locations`) come from a different source: GPA's own
nationwide store-locator file, a plain static JSON with no bot check - it lists every banner GPA runs
("Minuto PA", "Posto Pão de Açúcar", ...), so only entries whose own type is this chain's name are kept.
It gives no coordinates, so they are geocoded like Mercadinho's and Pinheiro's.
"""

import json
import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from scraper.base import BranchLocation, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper

logger = logging.getLogger(__name__)

_PRICE = r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"
_PRICE_RE = re.compile(_PRICE)
_DEAL_PRICE_RE = re.compile(r"sai por\s*" + _PRICE, re.IGNORECASE)
# "10% na 2ª unidade" / "Leve 3 e pague 2": only cheaper when buying several.
_MULTI_BUY_RE = re.compile(r"\d+%\s+na\s+\d+\S*\s+unidade|leve\s+\d+\s+e\s+pague\s+\d+", re.IGNORECASE)
_OFFER_RE = re.compile(r"\d+%\s*OFF|" + _MULTI_BUY_RE.pattern, re.IGNORECASE)
_PRODUCT_HREF = "/produto/"


class PaoDeAcucarScraper(BaseScraper):
    site_name = "Pão de Açúcar"
    site_key = "pao_de_acucar"
    base_url = "https://www.paodeacucar.com"
    offers_url = base_url

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        """Scrape the offers on the home page (``query`` is ignored)."""
        logger.info("[%s] Starting scrape (limit=%d)", self.site_name, limit)
        try:
            soup = self.render(self.offers_url, wait_seconds=6, scroll=True)
        finally:
            self.close()

        title = soup.title.get_text(strip=True) if soup.title else ""
        if "verificação de segurança" in title.lower():
            raise RuntimeError("Pão de Açúcar served its bot check instead of the home page")

        results = self.parse_offers(soup, limit=limit)
        logger.info("[%s] Home page yielded %d products", self.site_name, len(results))
        if not results:
            logger.warning("[%s] No product cards found; markup may have changed", self.site_name)
        return results

    def fetch_locations(self) -> List[BranchLocation]:
        """The chain's real, physical branches: GPA's own nationwide store-locator file, filtered to ours.

        It is a plain static JSON, unlike the bot-protected offers page, so a plain request answers it. It
        lists every store GPA runs nationwide, under several banners ("Minuto PA", "Posto Pão de Açúcar",
        ...) and every state, so it is filtered twice: to this chain's own banner, and to Ceará - this app
        compares prices in and around Fortaleza, so a branch a thousand kilometres away in another state
        would only add noise (and an unnecessary geocoding call) for no shopper it could ever be "near". It
        gives no coordinates, so a kept branch is geocoded like Mercadinho's and Pinheiro's.
        """
        try:
            payload = json.loads(self.fetch_raw(
                "https://static.gpa.digital/json/locator/store-locator-pa.json",
            ))
        except Exception as exc:
            logger.warning("[%s] Could not fetch the branch list: %s", self.site_name, exc)
            return []
        branches, seen = [], set()
        for item in payload:
            if (item.get("tipo") or "").strip() != self.site_name:
                continue
            if (item.get("estado") or "").strip() not in ("Ceará", "CE"):
                continue
            name, address = self._branch_name_address(item)
            if not name or not address or name in seen:
                continue
            seen.add(name)
            branches.append(BranchLocation(external_id=name, name=name, address=address))
        logger.info("[%s] %d real branch(es) found (in Ceará)", self.site_name, len(branches))
        return branches

    @staticmethod
    def _branch_name_address(item: dict) -> tuple:
        name = (item.get("nome") or "").strip()
        parts = [item.get("endereco"), item.get("bairro"), item.get("cidade")]
        address = ", ".join(re.sub(r"\s+", " ", p).strip(" -") for p in parts if p and p.strip(" -"))
        return name, address

    def parse_offers(self, soup: BeautifulSoup, limit: int = 1000) -> List[ProductPrice]:
        """Extract one :class:`ProductPrice` per distinct product on the page.

        Carousels repeat cards (slick clones them for infinite scrolling), so
        products are de-duplicated by the id in their URL.
        """
        results: List[ProductPrice] = []
        seen = set()
        for link in soup.select(f'a[href^="{_PRODUCT_HREF}"]'):
            href = link["href"]
            product_id = href.split("/")[2] if href.count("/") >= 2 else href
            if product_id in seen:
                continue
            seen.add(product_id)

            card = self._card_for(link)
            product = self._parse_card(card, href) if card is not None else None
            if product is None:
                continue
            results.append(product)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _card_for(link: Tag) -> Optional[Tag]:
        """Smallest ancestor of ``link`` that shows a price for that product only."""
        product_href = link["href"]
        node = link.parent
        while node is not None and node.name not in ("body", "html"):
            hrefs = {a["href"] for a in node.select(f'a[href^="{_PRODUCT_HREF}"]')}
            if hrefs - {product_href}:
                return None  # grew past this card into a neighbour
            if _PRICE_RE.search(node.get_text(" ", strip=True)):
                return node
            node = node.parent
        return None

    def _parse_card(self, card: Tag, href: str) -> Optional[ProductPrice]:
        # The image link is empty and an outer link wraps name *and* price, so
        # the name is the shortest non-empty link text.
        link_texts = [a.get_text(strip=True) for a in card.select(f'a[href^="{_PRODUCT_HREF}"]')]
        link_texts = [t for t in link_texts if t]
        if link_texts:
            name = min(link_texts, key=len)
        else:
            img = card.find("img", alt=True)
            name = img["alt"].strip() if img else ""
        if not name:
            return None

        text = card.get_text(" ", strip=True)
        regular = self._clean_price(_PRICE_RE.search(text).group(1))
        deal_match = _DEAL_PRICE_RE.search(text)
        deal_price = self._clean_price(deal_match.group(1)) if deal_match else None
        offer_match = _OFFER_RE.search(text)
        offer = offer_match.group(0) if offer_match else None

        # A multi-buy deal only pays off for 2+ units; a shopper buying one
        # still pays the regular price, so that is what we record.
        multi_buy = bool(offer and _MULTI_BUY_RE.fullmatch(offer))
        price = deal_price if deal_price and not multi_buy and deal_price < regular else regular
        return ProductPrice(
            store_name=self.site_name,
            product_name=name,
            price=price,
            url=self._make_absolute(href),
            regular_price=regular if price != regular else None,
            offer=offer,
        )
