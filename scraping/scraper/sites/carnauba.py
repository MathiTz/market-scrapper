"""Carnaúba Supermercados scraper: a storefront on the Mercadapp platform (see :mod:`scraper.mercadapp`),
the same one Mercadinho São Luiz runs on. Its ``loja/79`` is Fortaleza's own storefront; ``brand_id``
and ``market_id`` (79) were confirmed from the requests the storefront itself makes on load.
"""

from scraper.mercadapp import MercadappScraper


class CarnaubaScraper(MercadappScraper):
    site_name = "Carnaúba Supermercados"
    site_key = "carnauba"
    base_url = "https://carnaubasupermercados.com.br"
    offers_url = "https://carnaubasupermercados.com.br/loja/79/ofertas"
    brand_id = "27"
