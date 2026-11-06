"""Sam's Club scraper.

Sam's Club runs on VTEX, so its offers come from the public product search API
(see :mod:`scraper.vtex`); the old approach rendered the page and found no
prices. The daily run collects the discounted grocery-type products, best discounts first. The weekly full run
(``full_catalogue``) reads the whole grocery-type catalogue at its current price, each department a subcategory
at a time so none is cut at the search API's page limit; the store also sells furniture, electronics and so on,
which are left out.
"""

from scraper.vtex import VtexScraper


class SamsClubScraper(VtexScraper):
    site_name = "Sams Club"
    site_key = "sams_club"
    base_url = "https://www.samsclub.com.br"
    offers_url = base_url + "/ofertas-plus"
    split_subcategories = True  # for the weekly full run; the daily run reads only the discounted products
    categories = (
        "acougue", "bebidas", "vinhos", "mercearia", "mercearia-doce", "hortifruti", "congelados",
        "frios-e-laticinios", "padaria-e-confeitaria", "limpeza", "beleza-higiene-e-saude",
    )
