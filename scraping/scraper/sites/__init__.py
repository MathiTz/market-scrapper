"""Site-specific scraper implementations and registry."""

from scraper.sites.assai import AssaiScraper
from scraper.sites.atacadao import AtacadaoScraper
from scraper.sites.carnauba import CarnaubaScraper
from scraper.sites.centerbox import CenterboxScraper
from scraper.sites.cometa import CometaScraper
from scraper.sites.gbarbosa import GBarbosaScraper
from scraper.sites.mercadinho import MercadinhoScraper
from scraper.sites.mix_mateus import MixMateusScraper
from scraper.sites.pao_de_acucar import PaoDeAcucarScraper
from scraper.sites.pinheiro import PinheiroScraper
from scraper.sites.sams_club import SamsClubScraper

ALL_SCRAPERS = [
    AtacadaoScraper,
    CarnaubaScraper,
    CenterboxScraper,
    CometaScraper,
    GBarbosaScraper,
    MercadinhoScraper,
    MixMateusScraper,
    PaoDeAcucarScraper,
    PinheiroScraper,
    SamsClubScraper,
]

# Chains that publish no prices, only flyers and branches: not scraped for offers, but their branches are synced.
FLYER_ONLY_SCRAPERS = [
    AssaiScraper,
]

# Build a map from site_key (or fallback to site_name) to scraper class
SCRAPER_MAP = {}
for scraper_cls in ALL_SCRAPERS:
    key = getattr(scraper_cls, "site_key", None) or scraper_cls.site_name.lower().replace(" ", "_")
    SCRAPER_MAP[key] = scraper_cls

__all__ = [
    "ALL_SCRAPERS", "FLYER_ONLY_SCRAPERS", "SCRAPER_MAP", "AssaiScraper", "AtacadaoScraper", "CarnaubaScraper", "CenterboxScraper", "CometaScraper", "GBarbosaScraper", "MercadinhoScraper", "MixMateusScraper",
    "MixMateusScraper", "PaoDeAcucarScraper", "PinheiroScraper", "SamsClubScraper",
]
