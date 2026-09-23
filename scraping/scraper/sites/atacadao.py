"""Atacadão scraper.

Atacadão runs on VTEX (see :mod:`scraper.vtex`). It sells at everyday wholesale
prices and no product in its catalog carries a discount (0 of 600 sampled), so
this collects a price list: the first products of each grocery category at their
current price, with no deal label. Prices are those of the site's default
region and may differ per store.
"""

from scraper.vtex import VtexScraper


class AtacadaoScraper(VtexScraper):
    site_name = "Atacadão"
    site_key = "atacadao"
    base_url = "https://www.atacadao.com.br"
    offers_url = base_url
    only_discounted = False
    categories = (
        "mercearia", "frios-e-congelados", "bebidas", "higiene-e-perfumaria", "limpeza",
        "hortifruti", "carnes-aves-e-peixes", "padaria-e-matinais",
    )
