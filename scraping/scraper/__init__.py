"""Scraper package for market data collection."""

from scraper.base import BaseScraper, ProductPrice
from scraper.scrapling_scraper import ScraplingBaseScraper

__all__ = ["BaseScraper", "ProductPrice", "ScraplingBaseScraper"]
