"""Shared scraper for storefronts built on the Mercadapp platform (Mercadinho São Luiz, Carnaúba).

The storefront ("loja/<market_id>") loads its offers as JSON, one request per section, and renders only a
fraction of them. So the scraper lets the page log itself in, captures those JSON responses and reads the
products from them: name, price, regular price, stock and how long the offer lasts. If nothing is captured
it falls back to reading the rendered cards, as it did before.

It is a React SPA: the homepage and ``/ofertas`` both return an empty shell, and products are loaded
client-side. We use Selenium to render the page, dismiss any modal, click "Ver todos" to show all products
in the carousel, and then extract all product cards from the DOM.

Subclasses set ``site_name``, ``site_key``, ``base_url``, ``offers_url`` and ``brand_id`` (the platform's id
for the chain, used by :meth:`fetch_locations` to list its real branches).
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper
from scraper.base import BranchLocation, ProductPrice

logger = logging.getLogger(__name__)


# Runs in the page before its own scripts: keeps the body of every offers response the page receives, so
# the site's own login is used and nothing has to be imitated.
_CAPTURE_JS = r"""
(() => {
  window.__captured = [];
  const wanted = (u) => /\/items\/offers/.test(u);
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const u = typeof args[0] === 'string' ? args[0] : args[0].url;
      if (wanted(u)) res.clone().text().then((t) => window.__captured.push(t));
    } catch (e) {}
    return res;
  };
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.addEventListener('load', () => {
      try { if (wanted(String(url))) window.__captured.push(this.responseText); } catch (e) {}
    });
    return open.apply(this, arguments);
  };
})();
"""

# Keeps the body of every drivethru_markets response: the chain's real, physical branches (see
# fetch_locations). Loaded the same way as the offers capture above, and for the same reason: the
# storefront's own guest session is used rather than imitated.
_LOCATIONS_CAPTURE_JS = r"""
(() => {
  window.__branches = [];
  const wanted = (u) => /drivethru_markets/.test(u);
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const u = typeof args[0] === 'string' ? args[0] : args[0].url;
      if (wanted(u)) res.clone().text().then((t) => window.__branches.push(t));
    } catch (e) {}
    return res;
  };
})();
"""


def _parse_time(value) -> Optional[datetime]:
    """An ISO timestamp with an offset ("2026-09-30T20:00:00.000-03:00") as an aware datetime, or None."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class MercadappScraper(BaseScraper):
    brand_id: str = ""  # the platform's id for the chain; subclasses set it

    product_url_keywords = (
        "produtos", "categoria", "ofertas", "promocoes",
        "promocao", "busca",
    )
    product_card_selectors = (
        "div.store-card-product",
        "div.card-product",
        "div.product", "div.product-card", "div.product-item",
        "div.card", "article.product", "li.product",
        "div[class*=\"product\"]", "div[class*=\"card\"]",
        "div[class*=\"item\"]",
    )
    product_name_selectors = (
        "div.product-description p:last-child",
        "p:last-child",
        ".product-name", "h2.product-name", "h3.product-name",
        ".name", "h2", "h3", ".product-title",
        "span[class*=\"name\"]", "div[class*=\"name\"]",
    )
    product_price_selectors = (
        "p.current-price-product",
        ".price", ".product-price", ".price-box", ".sale-price",
        ".selling-price", ".best-price", ".price-value",
        "span[class*=\"price\"]",
    )
    product_link_selectors = ("a.product-link", "a")

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        """Scrape all offers: from the JSON the page loads, or from its rendered cards if that yields nothing."""
        logger.info("[%s] Starting scrape (limit=%d)", self.site_name, limit)
        products = self._scrape_json(limit)
        if products:
            self._log_sample(products)
            return products
        logger.warning("[%s] No offers captured from the page's JSON; reading the rendered cards", self.site_name)
        return self._scrape_cards(limit)

    def _scrape_json(self, limit: int) -> List[ProductPrice]:
        try:
            self._driver = self._create_driver()
            self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _CAPTURE_JS})
            self._driver.get(self.offers_url)
            bodies = self._wait_for_offers(self._driver)
        except Exception as exc:
            logger.warning("[%s] Could not capture the offers JSON: %s", self.site_name, exc)
            return []
        finally:
            self.close()
        products = self.parse_offers(bodies, limit=limit)
        logger.info("[%s] %d response(s) captured, %d product(s) on offer", self.site_name, len(bodies), len(products))
        return products

    @staticmethod
    def _wait_for_offers(driver, timeout: int = 50, settle: int = 6) -> List[str]:
        """The offers responses the page has received, once no new ones have arrived for ``settle`` seconds."""
        deadline = time.monotonic() + timeout
        count, unchanged = 0, 0.0
        while time.monotonic() < deadline:
            time.sleep(2)
            current = driver.execute_script("return window.__captured.length")
            if current and current == count:
                unchanged += 2
                if unchanged >= settle:
                    break
            else:
                count, unchanged = current, 0.0
        return driver.execute_script("return window.__captured") or []

    def parse_offers(self, bodies: Iterable[str], limit: int = 1000,
                     now: Optional[datetime] = None) -> List[ProductPrice]:
        """Products from the offers responses; sold-out, expired and not-yet-started offers are left out."""
        now = now or datetime.now(timezone.utc)
        seen, products = set(), []
        for body in bodies:
            try:
                data = json.loads(body)
            except (TypeError, ValueError):
                continue
            for mix in (data.get("mixes") or []) if isinstance(data, dict) else []:
                for item in mix.get("items") or []:
                    product = self._offer_to_product(item, now)
                    if product is None or item["id"] in seen:
                        continue
                    seen.add(item["id"])
                    products.append(product)
        return products[:limit]

    def _offer_to_product(self, item: dict, now: datetime) -> Optional[ProductPrice]:
        name = (item.get("description") or item.get("short_description") or "").strip()
        price = item.get("price")
        if item.get("id") is None or not name or not isinstance(price, (int, float)) or price <= 0:
            return None
        stock = item.get("stock")
        if isinstance(stock, (int, float)) and stock <= 0:
            return None  # sold out
        for offer in item.get("offers") or []:
            start, end = _parse_time(offer.get("start_at")), _parse_time(offer.get("end_at"))
            if (start and start > now) or (end and end < now and not offer.get("unlimited_end")):
                return None  # not started yet, or already over
        regular = item.get("original_price")
        discounted = isinstance(regular, (int, float)) and regular > price
        label = (item.get("offer_title") or "").strip() or (
            f"{round((1 - price / regular) * 100)}% OFF" if discounted else None
        )
        return ProductPrice(
            store_name=self.site_name,
            product_name=name,
            price=float(price),
            url=self.offers_url,
            regular_price=float(regular) if discounted else None,
            offer=label,
            stock=int(stock) if isinstance(stock, (int, float)) else None,
        )

    def fetch_locations(self) -> List[BranchLocation]:
        """The chain's real, physical branches (name and address; no coordinates - see services.store_locations).

        The storefront only asks for this list once its delivery-method dialog opens, so the scraper opens
        it; if that fails the capture simply stays empty and the caller gets nothing, which is safer than a
        stale or wrong branch list.
        """
        driver = None
        try:
            driver = self._create_driver()
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": _LOCATIONS_CAPTURE_JS})
            driver.get(self.base_url)
            time.sleep(4)
            self._open_delivery_method_dialog(driver)
            bodies = self._wait_for_branches(driver)
        except Exception as exc:
            logger.warning("[%s] Could not capture the branch list: %s", self.site_name, exc)
            return []
        finally:
            if driver is not None:
                driver.quit()
        branches = self._parse_locations(bodies)
        logger.info("[%s] %d real branch(es) found", self.site_name, len(branches))
        return branches

    @staticmethod
    def _wait_for_branches(driver, timeout: int = 20) -> List[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if driver.execute_script("return window.__branches.length"):
                break
            time.sleep(1)
        return driver.execute_script("return window.__branches") or []

    @staticmethod
    def _parse_locations(bodies: Iterable[str]) -> List[BranchLocation]:
        branches, seen = [], set()
        for body in bodies:
            try:
                data = json.loads(body)
            except (TypeError, ValueError):
                continue
            items = data.get("data", data) if isinstance(data, dict) else data
            for item in items or []:
                branch_id, name, address = item.get("id"), (item.get("name") or "").strip(), (item.get("address") or "").strip()
                if branch_id is None or not name or not address or branch_id in seen:
                    continue
                seen.add(branch_id)
                branches.append(BranchLocation(external_id=str(branch_id), name=name, address=address))
        return branches

    def _scrape_cards(self, limit: int) -> List[ProductPrice]:
        """The previous approach: read the cards the page renders (only a fraction of the offers)."""
        # Ensure driver is created
        if self._driver is None:
            self._driver = self._create_driver()

        try:
            logger.info("[%s] Rendering offers page: %s", self.site_name, self.offers_url)
            self._driver.get(self.offers_url)
            self._wait_for_products(timeout=20)  # this page often never renders cards; the homepage does

            # Dismiss any modal that appears
            self._dismiss_modal()

            # Click "Ver todos" buttons to expand carousels
            self._click_show_all()

            # Scroll to load lazy content if any
            self._scroll_to_bottom()

            # After scrolling, click "Ver todos" again (some may appear later)
            self._click_show_all()

            soup = BeautifulSoup(self._driver.page_source, "lxml")
            results = self.extract_products(soup, limit=limit)
            logger.info("[%s] Offers page yielded %d products", self.site_name, len(results))
            if results:
                self._log_sample(results)
                self.close()
                return results
            logger.warning("[%s] No products found on offers page", self.site_name)
        except Exception as e:
            logger.warning("[%s] Offers page failed: %s", self.site_name, e)

        # Fallback: render homepage and discover product URLs
        try:
            if self._driver is None:
                self._driver = self._create_driver()
            logger.info("[%s] Rendering homepage: %s", self.site_name, self.base_url)
            self._driver.get(self.base_url)
            self._wait_for_products()
            self._dismiss_modal()
            self._click_show_all()
            self._scroll_to_bottom()
            self._click_show_all()
            soup = BeautifulSoup(self._driver.page_source, "lxml")
            results = self.extract_products(soup, limit=limit)
            logger.info("[%s] Homepage yielded %d products", self.site_name, len(results))
            if results:
                self._log_sample(results)
                self.close()
                return results
            logger.warning("[%s] No products found on homepage", self.site_name)
        except Exception as e:
            logger.error("[%s] Homepage fallback failed: %s", self.site_name, e)
        self.close()
        return []

    def _wait_for_products(self, timeout: int = 45) -> None:
        """Wait until product cards are rendered.

        The SPA's load time varies from a few seconds to 20+, so a fixed sleep
        sometimes captured the page before any card existed (0 products).
        """
        try:
            WebDriverWait(self._driver, timeout).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "div.card-product")
            )
        except TimeoutException:
            logger.warning("[%s] No product cards after %ds", self.site_name, timeout)

    def _dismiss_modal(self) -> None:
        """Click a close button or backdrop to dismiss any modal."""
        try:
            # Try common close buttons
            close_selectors = [
                "button.close",
                "button[aria-label='Close']",
                "button[aria-label='Fechar']",
                ".modal .close",
                ".MuiDialog-root button[aria-label='Close']",
                ".MuiDialog-root button[aria-label='Fechar']",
                ".modal button",
                ".MuiDialog-root button",
                "button[class*='close']",
                ".close-btn",
                "[data-dismiss='modal']",
            ]
            for sel in close_selectors:
                elements = self._driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    try:
                        elements[0].click()
                        logger.info("[%s] Dismissed modal via %s", self.site_name, sel)
                        time.sleep(2)
                        return
                    except Exception:
                        continue

            # Try clicking on a modal backdrop
            backdrops = self._driver.find_elements(By.CSS_SELECTOR, ".modal-backdrop, .MuiBackdrop-root")
            if backdrops:
                try:
                    backdrops[0].click()
                    logger.info("[%s] Dismissed modal via backdrop", self.site_name)
                    time.sleep(2)
                    return
                except Exception:
                    pass

            # Try pressing Escape
            body = self._driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
            logger.info("[%s] Pressed Escape to dismiss modal", self.site_name)
            time.sleep(2)
        except Exception as e:
            logger.debug("[%s] No modal to dismiss or failed: %s", self.site_name, e)

    @classmethod
    def _open_delivery_method_dialog(cls, driver) -> None:
        """Open the "Selecione um método de entrega" dialog: it is what makes the page ask for the branch list.

        Some storefronts open it themselves on a fresh session, but not reliably (a remembered choice can
        skip it), so it is opened by hand. Headless Chrome sometimes reports the trigger "not interactable"
        on a plain click even once present, so a scroll-into-view and a JS-dispatched click are tried too.
        """
        try:
            trigger = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Selecione um método de entr')]"))
            )
            cls._robust_click(driver, trigger)
            time.sleep(1)
            for text in ("CLIQUE E RETIRE", "Clique e retire", "Clique e Retire"):
                buttons = driver.find_elements(By.XPATH, f"//*[contains(text(),'{text}')]")
                if buttons:
                    cls._robust_click(driver, buttons[0])
                    break
            time.sleep(3)
        except Exception as exc:
            logger.debug("Could not open the delivery-method dialog: %s", exc)

    @staticmethod
    def _robust_click(driver, element) -> None:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)

    def _click_show_all(self) -> None:
        """Click all 'Ver todos' buttons to expand product carousels."""
        try:
            buttons = self._driver.find_elements(By.XPATH, "//button[contains(., 'Ver todos')]")
            logger.info("[%s] Found %d 'Ver todos' buttons", self.site_name, len(buttons))
            for btn in buttons:
                try:
                    btn.click()
                    time.sleep(3)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("[%s] Failed to click 'Ver todos': %s", self.site_name, e)

    def _scroll_to_bottom(self) -> None:
        """Scroll the page to trigger lazy loading."""
        try:
            last_height = self._driver.execute_script("return document.body.scrollHeight")
            for _ in range(10):  # max 10 scrolls
                self._driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self._driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
        except Exception as e:
            logger.debug("[%s] Scroll failed: %s", self.site_name, e)

    def _log_sample(self, products: List[ProductPrice]) -> None:
        """Log the first few products for debugging."""
        for p in products[:5]:
            logger.info(
                "[%s] Sample product: %s - R$ %.2f - %s",
                self.site_name,
                p.product_name,
                p.price,
                p.url,
            )
