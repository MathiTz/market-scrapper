"""Sam's Club scraper.

Sam's Club runs on VTEX, so its offers come from the public product search API
(see :mod:`scraper.vtex`); the old approach rendered the page and found no
prices. Only discounted grocery-type products are collected, best discounts
first; the store also sells furniture, electronics and so on.
"""

from scraper.vtex import VtexScraper


class SamsClubScraper(VtexScraper):
    site_name = "Sams Club"
    site_key = "sams_club"
    base_url = "https://www.samsclub.com.br"
    offers_url = base_url + "/ofertas-plus"
    only_discounted = True
    categories = (
        "acougue", "bebidas", "vinhos", "mercearia", "mercearia-doce", "hortifruti", "congelados",
        "frios-e-laticinios", "padaria-e-confeitaria", "limpeza", "beleza-higiene-e-saude",
    )
