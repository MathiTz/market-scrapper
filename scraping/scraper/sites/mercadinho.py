"""Mercadinho São Luiz scraper: a storefront on the Mercadapp platform (see :mod:`scraper.mercadapp`)."""

from scraper.mercadapp import MercadappScraper


class MercadinhoScraper(MercadappScraper):
    site_name = "Mercadinho São Luiz"
    site_key = "mercadinho"
    base_url = "https://mercadinhossaoluiz.com.br"
    offers_url = "https://mercadinhossaoluiz.com.br/loja/355/ofertas"
    brand_id = "221"
