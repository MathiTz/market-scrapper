"""Base scraper using Scrapling for fetching and rendering.

This module provides a drop-in replacement for :class:`BaseScraper` that
uses the `Scrapling <https://github.com/d4vinci/Scrapling>`_ library
instead of raw ``requests`` + ``BeautifulSoup`` and Selenium.  It is
intended to be used by site-specific scrapers that need a more robust
fetching/rendering pipeline (stealth mode, auto retries, etc.).
"""

import logging
import time
from typing import Callable, List, Optional

from bs4 import BeautifulSoup

from scraper.base import (
    SCROLL_PAUSE_SECONDS,
    SCROLL_STEP_PX,
    SCROLL_STEPS,
    BaseScraper,
    ProductPrice,
)

logger = logging.getLogger(__name__)


def _scroll_page(page):
    """Playwright page action: scroll down in steps to trigger lazy loading.

    Uses ``window.scrollBy`` rather than ``mouse.wheel``; the wheel event did
    not trigger the lazy-loaded sections on Pão de Açúcar in headless mode.
    """
    for _ in range(SCROLL_STEPS):
        page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX})")
        page.wait_for_timeout(int(SCROLL_PAUSE_SECONDS * 1000))
    page.evaluate("window.scrollTo(0, 0)")
    return page


try:
    from scrapling.fetchers import Fetcher, StealthyFetcher
except ImportError:  # pragma: no cover - only when scrapling is not installed
    Fetcher = None
    StealthyFetcher = None


class ScraplingBaseScraper(BaseScraper):
    """A scraper that uses Scrapling for fetching and rendering.

    This class extends :class:`BaseScraper` but overrides :meth:`fetch`
    and :meth:`render` to use Scrapling's ``Fetcher`` and ``StealthyFetcher``
    respectively.  If Scrapling is not installed, it falls back to the
    original ``requests`` + ``Selenium`` implementation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scrapling_available = Fetcher is not None
        if not self._scrapling_available:
            logger.warning("Scrapling is not installed; falling back to requests+Selenium.")

    def fetch(self, url: str, params: Optional[dict] = None) -> BeautifulSoup:
        """Fetch a URL using Scrapling's Fetcher (or requests fallback)."""
        if not self._scrapling_available:
            return super().fetch(url, params=params)

        logger.info("Scrapling fetching %s with params=%s", url, params)
        if params:
            from urllib.parse import urlencode
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(params)}"

        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # Fetcher.get is a classmethod
                page = Fetcher.get(url)
                html = str(page.html_content)  # not page.text: that is the element text ("None") on a Response
                return BeautifulSoup(html, "lxml")
            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Scrapling fetch attempt %d failed for %s: %s. Retrying in %.1fs",
                        attempt, url, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("All %d Scrapling fetch attempts failed for %s: %s",
                                 self.max_retries, url, e)
        logger.warning("Scrapling fetch failed (%s); falling back to requests", last_exc)
        return super().fetch(url, params=params)

    def render(
        self,
        url: str,
        wait_seconds: int = 5,
        scroll: bool = False,
        page_action: Optional[Callable] = None,
    ) -> BeautifulSoup:
        """Render a JS-heavy page using Scrapling's StealthyFetcher.

        ``page_action`` is called with the Playwright page once it has loaded (and must return it), for
        reading things the rendered HTML does not hold. Scrapling logs an error from it and carries on
        rather than raising, so the caller has to check what it collected.
        """
        if not self._scrapling_available:
            return super().render(url, wait_seconds=wait_seconds, scroll=scroll)

        logger.info("Scrapling rendering %s (wait %ds, scroll=%s)", url, wait_seconds, scroll)
        fetch_kwargs = {}
        if page_action is not None:
            fetch_kwargs["page_action"] = page_action
        elif scroll:
            fetch_kwargs["page_action"] = _scroll_page
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # StealthyFetcher.fetch is a classmethod; wait is in milliseconds
                page = StealthyFetcher.fetch(
                    url,
                    headless=True,
                    wait=wait_seconds * 1000,
                    **fetch_kwargs,
                )
                html = str(page.html_content)  # not page.text: that is the element text ("None") on a Response
                return BeautifulSoup(html, "lxml")
            except Exception as e:
                last_exc = e
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Scrapling render attempt %d failed for %s: %s. Retrying in %.1fs",
                        attempt, url, e, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("All %d Scrapling render attempts failed for %s: %s",
                                 self.max_retries, url, e)
        logger.warning("Scrapling render failed (%s); falling back to Selenium", last_exc)
        return super().render(url, wait_seconds=wait_seconds, scroll=scroll)

    def scrape(self, query: str, limit: int = 20) -> List[ProductPrice]:
        """Scrape product prices (subclasses must implement)."""
        raise NotImplementedError
