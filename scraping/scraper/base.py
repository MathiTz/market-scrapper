"""Base scraper class shared by all site-specific scrapers."""

import logging
import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)

# Retry configuration - can be overridden via env vars
MAX_RETRIES = int(os.getenv("SCRAPE_MAX_RETRIES", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("SCRAPE_RETRY_BACKOFF", "2.0"))
DEFAULT_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "15"))

# Lazy-load scrolling used by render(scroll=True)
SCROLL_STEPS = 14
SCROLL_STEP_PX = 900
SCROLL_PAUSE_SECONDS = 0.7


@dataclass
class ProductPrice:
    """A scraped product price entry."""
    store_name: str
    product_name: str
    price: float
    url: str
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    # Set for promotions: the undiscounted price and the site's label for the deal.
    regular_price: Optional[float] = None
    offer: Optional[str] = None
    # Units the store says it has, when it says (None when unknown).
    stock: Optional[int] = None
    # The manufacturer's brand, barcode (EAN/GTIN) and a photo - set only by sources that actually give
    # them for free in the same response (VTEX's product search API does); most scrapers leave these None.
    brand: Optional[str] = None
    gtin: Optional[str] = None
    image_url: Optional[str] = None


@dataclass(frozen=True)
class BranchLocation:
    """A chain's real, physical branch: not the single placeholder ``Store.address``/``lat``/``lon``.

    ``lat``/``lon`` are ``None`` when the source gives only a text address; ``services.store_locations``
    geocodes those before they are stored, since a location with no coordinates is not usable for distance.
    """
    external_id: str  # the chain's own id for the branch, so a refresh updates it rather than duplicating it
    name: str
    address: str
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class ScrapeResult:
    """Result of a scrape attempt."""
    success: bool
    items_found: int = 0
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class BaseScraper(ABC):
    """Base class for site-specific scrapers.

    Subclasses must implement :meth:`scrape` and provide a
    ``site_name`` attribute.
    """

    site_name: str = "base"
    site_key: str = "base"
    base_url: str = ""
    # Keywords used to identify product/offer pages from homepage links
    product_url_keywords: Tuple[str, ...] = (
        "colecao", "categoria", "produtos", "busca", "ofertas",
        "promocoes", "promocao", "especial", "meu-desconto",
    )
    # CSS selectors that typically wrap a product card
    product_card_selectors: Tuple[str, ...] = (
        "div.product-item", "div.product-card", "div.card",
        "li.product", "article.product", "div.product",
        "div.product-tile", "div.product-grid-item", "div.product-summary",
        "div.product-shelf", "div.product-list-item", "div.item",
        "div.product-shelf-item", "div.product-card-container",
        "div.shelf-item", "div.product-item-container",
        "div[class*=\"product\"]", "div[class*=\"card\"]",
        "div[class*=\"shelf\"]", "div[class*=\"item\"]",
    )
    # CSS selectors for product name, price, and link inside a card
    product_name_selectors: Tuple[str, ...] = (
        "h2.product-name", ".product-name", "h3.product-name",
        ".name", "h2", "h3", ".product-title", ".item-name",
        "[data-testid=\"product-name\"]", ".product-summary__name",
        ".product-card__name", "span[class*=\"name\"]",
        "div[class*=\"name\"]",
    )
    product_price_selectors: Tuple[str, ...] = (
        ".price", ".product-price", ".price-box", ".sale-price",
        ".product-price-value", ".price-value", ".item-price",
        "[data-testid=\"price\"]", ".selling-price", ".best-price",
        ".product-card__price", ".product-summary__price",
        ".list-price", ".sales-price", ".skuBestPrice",
        "span[class*=\"price\"]", "div[class*=\"price\"]",
    )
    product_link_selectors: Tuple[str, ...] = (
        "a.product-link", "a.product-name", "a.product-card__link", "a",
    )
    headers: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = MAX_RETRIES
    retry_backoff: float = RETRY_BACKOFF_SECONDS

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(self.headers)
        self._driver = None

    def __del__(self) -> None:
        self.close()

    def _fetch_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Fetch with retry logic for transient network errors."""
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("Attempt %d/%d fetching %s", attempt, self.max_retries, url)
                resp = getattr(self.session, method)(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout,
                    requests.HTTPError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Fetch attempt %d failed for %s: %s. Retrying in %.1fs",
                        attempt, url, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("All %d attempts failed for %s: %s",
                                 self.max_retries, url, exc)
        raise last_exc

    def fetch(self, url: str, params: Optional[dict] = None) -> BeautifulSoup:
        """Fetch a URL (with optional query params) and return parsed HTML."""
        logger.info("Fetching %s with params=%s", url, params)
        resp = self._fetch_with_retry(
            "get", url, params=params, timeout=self.timeout
        )
        return BeautifulSoup(resp.text, "lxml")

    def fetch_raw(self, url: str, params: Optional[dict] = None) -> str:
        """Fetch a URL and return raw text (for JSON APIs)."""
        logger.info("Fetching raw %s with params=%s", url, params)
        resp = self._fetch_with_retry(
            "get", url, params=params, timeout=self.timeout
        )
        return resp.text

    def render(self, url: str, wait_seconds: int = 5, scroll: bool = False) -> BeautifulSoup:
        """Use Selenium to render a JS-heavy page and return parsed HTML.

        With ``scroll=True`` the page is scrolled to the bottom in steps so
        lazy-loaded sections (carousels, infinite shelves) get rendered.
        """
        if self._driver is None:
            self._driver = self._create_driver()
        logger.info("Rendering %s with Selenium (wait %ds)", url, wait_seconds)
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._driver.get(url)
                time.sleep(wait_seconds)
                if scroll:
                    for _ in range(SCROLL_STEPS):
                        self._driver.execute_script(f"window.scrollBy(0, {SCROLL_STEP_PX});")
                        time.sleep(SCROLL_PAUSE_SECONDS)
                    self._driver.execute_script("window.scrollTo(0, 0);")
                html = self._driver.page_source
                return BeautifulSoup(html, "lxml")
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Render attempt %d failed for %s: %s. Retrying in %.1fs",
                        attempt, url, exc, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("All %d render attempts failed for %s: %s",
                                 self.max_retries, url, exc)
        raise last_exc

    def _create_driver(self):
        """Create a Chrome driver, handling common installation issues."""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"user-agent={self.headers['User-Agent']}")

        # 1) Selenium 4.6+ has built-in Selenium Manager - try this first
        try:
            logger.info("Trying Selenium Manager (built-in driver management)")
            return webdriver.Chrome(options=options)
        except Exception as e:
            logger.warning("Selenium Manager failed: %s", e)

        # 2) Try webdriver_manager, but search recursively for the actual binary
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver_path = ChromeDriverManager().install()
            logger.info("webdriver_manager returned path: %s", driver_path)

            # Search recursively in the cache dir for any valid chromedriver binary
            cache_root = os.path.expanduser("~/.wdm/drivers/chromedriver")
            found_path = None
            for root, dirs, files in os.walk(cache_root):
                for f in files:
                    full = os.path.join(root, f)
                    # Skip known non-binary files
                    if "third_party" in f.lower() or "license" in f.lower() or "notice" in f.lower():
                        continue
                    if self._is_valid_chromedriver(full):
                        found_path = full
                        break
                if found_path:
                    break
            if found_path:
                logger.info("Found chromedriver at: %s", found_path)
                return webdriver.Chrome(service=Service(found_path), options=options)

            # Also check the exact path returned (in case it's the real binary)
            if self._is_valid_chromedriver(driver_path):
                logger.info("Using chromedriver from webdriver_manager: %s", driver_path)
                return webdriver.Chrome(service=Service(driver_path), options=options)

            # Search the immediate directory of the returned path
            dir_path = os.path.dirname(driver_path)
            for f in os.listdir(dir_path):
                full = os.path.join(dir_path, f)
                if self._is_valid_chromedriver(full):
                    logger.info("Found actual chromedriver in cache dir: %s", full)
                    return webdriver.Chrome(service=Service(full), options=options)

            logger.warning("webdriver_manager returned non-executable path: %s", driver_path)
        except Exception as e:
            logger.warning("webdriver_manager failed: %s", e)

        # 3) Fallback: try to find chromedriver in PATH or common locations
        candidates = [
            shutil.which("chromedriver"),
            "/usr/local/bin/chromedriver",
            "/opt/homebrew/bin/chromedriver",
            "/usr/bin/chromedriver",
        ]
        for path in candidates:
            if path and self._is_valid_chromedriver(path):
                logger.info("Using chromedriver at %s", path)
                return webdriver.Chrome(service=Service(path), options=options)

        # If all else fails, raise
        raise RuntimeError("Could not find a usable chromedriver. Please install it.")

    def _is_valid_chromedriver(self, path: str) -> bool:
        """Check if a path is a valid chromedriver executable.

        Checks name/content first, then repairs a missing execute bit rather
        than rejecting an otherwise-valid binary. This matters because
        Chrome-for-Testing driver archives can extract 'chromedriver' without
        the executable bit set, while the unrelated THIRD_PARTY_NOTICES text
        file sometimes keeps an executable bit from the archive - checking
        os.X_OK first would reject the real binary and accept the notice.
        """
        if not path or not os.path.isfile(path):
            return False
        # Exclude known non-binary files
        basename = os.path.basename(path).lower()
        if "third_party" in basename or "license" in basename or "notice" in basename:
            return False
        is_binary = False
        # Check if it's a binary by reading first few bytes (Mach-O or ELF)
        try:
            with open(path, "rb") as f:
                header = f.read(4)
            # Mach-O magic: 0xfeedface, 0xfeedfacf, 0xcefaedfe, 0xcffaedfe
            # (the latter two are the byte-swapped 32/64-bit forms actually
            # found on disk for arm64 chromedriver builds)
            # ELF magic: 0x7f454c46
            if header in (b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
                is_binary = True
        except OSError:
            pass
        if not is_binary:
            # Fallback: check if it's not a text file (contains null bytes)
            try:
                with open(path, "rb") as f:
                    data = f.read(1024)
                if b"\x00" in data:
                    is_binary = True
            except OSError:
                pass
        if not is_binary:
            return False
        if not os.access(path, os.X_OK):
            try:
                current_mode = os.stat(path).st_mode
                os.chmod(path, current_mode | 0o111)
                logger.info("Restored execute permission on %s", path)
            except OSError as e:
                logger.warning("Could not chmod +x %s: %s", path, e)
                return False
        return os.access(path, os.X_OK)

    def close(self) -> None:
        """Close the Selenium driver if open."""
        if self._driver:
            self._driver.quit()
            self._driver = None

    def find_product_urls(self, soup: BeautifulSoup, limit: int = 10) -> List[str]:
        """Find URLs of product listing pages from a parsed homepage."""
        found = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            href_lower = href.lower()
            if any(k in href_lower for k in self.product_url_keywords) or \
               any(k in text for k in self.product_url_keywords):
                url = self._make_absolute(href)
                if url not in seen:
                    seen.add(url)
                    found.append(url)
                    if len(found) >= limit:
                        break
        logger.info("Found %d product URLs", len(found))
        return found

    def _make_absolute(self, href: str) -> str:
        """Convert a possibly-relative href to an absolute URL."""
        if href.startswith("http"):
            return href
        return self.base_url.rstrip("/") + "/" + href.lstrip("/")

    def extract_products(self, soup: BeautifulSoup, limit: int) -> List[ProductPrice]:
        """Extract ALL product cards from a parsed page using known selectors.

        Instead of stopping at the first selector that matches, we collect
        cards from ALL selectors, deduplicate them (by their HTML string),
        and then extract product info from each.
        """
        results = []
        card_set = set()
        cards = []

        for sel in self.product_card_selectors:
            found = soup.select(sel)
            if found:
                logger.info("Selector '%s' found %d cards", sel, len(found))
            for c in found:
                key = str(c)
                if key not in card_set:
                    card_set.add(key)
                    cards.append(c)

        if not cards:
            logger.warning("No product cards found with any selector")
            return results

        logger.info("Total unique cards found: %d", len(cards))

        for card in cards[:limit]:
            name_el = None
            for sel in self.product_name_selectors:
                name_el = card.select_one(sel)
                if name_el:
                    break
            price_el = None
            for sel in self.product_price_selectors:
                price_el = card.select_one(sel)
                if price_el:
                    break
            link_el = None
            for sel in self.product_link_selectors:
                link_el = card.select_one(sel)
                if link_el:
                    break
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue
            price = 0.0
            if price_el:
                price = self._clean_price(price_el.get_text(strip=True))
            href = link_el.get("href") if link_el else ""
            url = self._make_absolute(href) if href else self.base_url
            results.append(
                ProductPrice(
                    store_name=self.site_name,
                    product_name=name,
                    price=price,
                    url=url,
                )
            )
        logger.info("Extracted %d products", len(results))
        return results

    @abstractmethod
    def scrape(self, query: str, limit: int = 20) -> List[ProductPrice]:
        """Scrape product prices from the site."""
        raise NotImplementedError

    def _clean_price(self, raw: str) -> float:
        """Parse a raw price string like 'R$ 12,34' or '12.34' into a float."""
        if not raw:
            return 0.0
        cleaned = raw.replace("R$", "").replace(" ", "").strip()
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
