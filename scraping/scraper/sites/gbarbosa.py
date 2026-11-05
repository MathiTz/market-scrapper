"""GBarbosa scraper.

GBarbosa runs on VTEX (see :mod:`scraper.vtex`). The site has a single price list for every area it delivers to
(the same product costs the same for a Fortaleza and an Aracaju postcode) and one seller, itself. Its catalogue is
about 43,000 products, most of them not food, so only the grocery and household departments are read, and each
one a subcategory at a time: Mercearia alone has almost 10,000 products, past what the search API returns for one
category. Prices are the everyday ones, with the list price and percentage shown when a product is discounted.

The pickup-points API lists no branches for this chain, so it has none in the app until a source for them is found.
"""

from scraper.vtex import VtexScraper


class GBarbosaScraper(VtexScraper):
    site_name = "GBarbosa"
    site_key = "gbarbosa"
    base_url = "https://www.gbarbosa.com.br"
    offers_url = base_url
    only_discounted = False
    split_subcategories = True
    categories = (
        "mercearia", "frios-e-laticinios", "congelados", "bebida-nao-alcoolica", "bebida-alcoolica",
        "higiene-e-beleza", "limpeza", "hortifruti", "carnes-e-aves", "peixaria", "padaria",
    )
