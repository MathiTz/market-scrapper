"""Frangolândia flyers: the chain has no scrapable price catalog online, but publishes its weekly flyers
("encartes") on its own WordPress site. This only lists them, as the same ``Encarte`` Cometa's flyers use -
the pages are shown to people as images, not read into prices (see the Encartes view in the UI).

``/wp-json/wp/v2/encarte`` gives each flyer's title, date and link; the flyer's page images are the
``e-gallery-item`` links of the Elementor gallery on the flyer's own page. The site posts a new flyer every
day or two and never removes old ones, so only the last ``MAX_AGE_DAYS`` days are listed (it gives no
validity window to go by).
"""

import html
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional

from scraper.base import ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper as BaseScraper
from scraper.sites.cometa import Encarte

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 14
MAX_FLYERS = 10

_GALLERY_IMAGE = re.compile(r'e-gallery-item[^>]*href="\s*(https://[^"\s]+\.(?:jpe?g|png|webp))"', re.IGNORECASE)


class FrangolandiaFlyers(BaseScraper):
    site_name = "Frangolândia"
    site_key = "frangolandia"
    base_url = "https://frangolandia.com"
    offers_url = base_url + "/encartes/"

    def scrape(self, query: str = "", limit: int = 1000) -> List[ProductPrice]:
        return []  # flyers only: there are no prices to read

    @staticmethod
    def parse_pages(page_html: str) -> List[str]:
        """The flyer page's own images, in order, without repeats."""
        return list(dict.fromkeys(_GALLERY_IMAGE.findall(page_html)))

    def fetch_encartes(self, now: Optional[datetime] = None) -> List[Encarte]:
        """The recently posted flyers, newest first; a flyer whose page has no images is left out."""
        cutoff = (now or datetime.now()) - timedelta(days=MAX_AGE_DAYS)
        items = json.loads(self.fetch_raw(f"{self.base_url}/wp-json/wp/v2/encarte", params={"per_page": MAX_FLYERS}))
        encartes = []
        for item in items:
            posted = datetime.fromisoformat(item["date"])
            if posted < cutoff:
                continue
            pages = self.parse_pages(self.fetch_raw(item["link"]))
            if not pages:
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", item["title"]["rendered"])).strip()
            encartes.append(Encarte(
                id=item["id"], name=title, description="", cover_url=pages[0], pdf_url=None,
                pages=pages, posted_at=posted.isoformat(),
            ))
        return encartes
