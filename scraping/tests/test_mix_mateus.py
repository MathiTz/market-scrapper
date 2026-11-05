"""Mix Mateus: flyers and branches from the group's flyers site, prices from the text of the flyers' PDFs."""

import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from scraper import flyer_pdf  # noqa: E402
from scraper.sites import SCRAPER_MAP  # noqa: E402
from scraper.sites.mix_mateus import MixMateusScraper  # noqa: E402
from services.public_api import _image_flyers  # noqa: E402
from tests.pdf_helpers import make_pdf, product  # noqa: E402

API = json.loads((Path(__file__).parent / "fixtures" / "mixmateus_api.json").read_text(encoding="utf-8"))
TODAY = datetime(2026, 11, 5, 12, 0)


def fake_api(asked=None):
    """``fetch_raw`` as the site's proxy answers it: the endpoint is the query parameter."""

    def fetch_raw(url, params=None):
        endpoint = params["endpoint"]
        if asked is not None:
            asked.append(endpoint)
        if endpoint == "/estados/CE/cidades":
            data = API["cities"]
        elif endpoint.startswith("/cidades/") and endpoint.endswith("/lojas"):
            data = API["stores"][endpoint.split("/")[2]]
        elif endpoint.startswith("/encartes/CE/fortaleza/"):
            data = API["encartes"]
        else:
            raise AssertionError(f"unexpected endpoint {endpoint}")
        return json.dumps({"status": "success", "data": data, "count": len(data)})

    return fetch_raw


def pdf_response(*cells):
    texts = [t for cell in cells for t in cell]
    return SimpleNamespace(content=make_pdf(texts))


class TestMixMateus(unittest.TestCase):
    def setUp(self):
        self.scraper = MixMateusScraper()

    def test_it_is_registered_under_its_key(self):
        self.assertIs(SCRAPER_MAP["mixmateus"], MixMateusScraper)

    def test_flyers_come_with_their_dates_and_a_pdf_link_the_site_serves(self):
        asked = []
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api(asked)):
            flyers = {e.name: e for e in self.scraper.fetch_encartes(now=TODAY)}
        self.assertEqual(sorted(flyers), ["Itambé", "Regular", "Seara"])
        regular = flyers["Regular"]
        self.assertEqual((regular.posted_at, regular.valid_until), ("2026-11-01T18:00:00", "2026-11-05T23:59:00"))
        self.assertEqual(regular.pdf_url, "https://ofertasmateus.com/api-proxy.php?file=uploads%2Fencartes%2F1793620425_6ae879c9d21e2.pdf")
        # the flyers are the same in every store: the first Mix Mateus one in Fortaleza is asked, with the brand
        self.assertIn("/encartes/CE/fortaleza/mix-henrique-jorge?marca=MA", asked)

    def test_a_flyer_that_has_ended_is_not_listed(self):
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()):
            names = {e.name for e in self.scraper.fetch_encartes(now=datetime(2026, 11, 6, 0, 30))}
        self.assertEqual(names, {"Itambé", "Seara"})  # "Regular" ended on 05/11 at 23:59

    def test_the_prices_printed_in_the_flyers_become_offers_the_lowest_where_repeated(self):
        arroz = product(60, 300, ["Arroz Camil", "Branco Tipo 1"], "4", "99")
        cheaper = product(60, 300, ["Arroz Camil", "Branco Tipo 1"], "4", "59")
        by_file = {"1793620425_6ae879c9d21e2": arroz,  # "Regular"
                   "1793824150_6aeb95961261f": cheaper}  # "Itambé"; "Seara" is a flat image: no text at all

        def get(method, url, **kwargs):
            return pdf_response(next((cell for key, cell in by_file.items() if key in url), []))

        today_only = MixMateusScraper.fetch_encartes
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()), \
                patch.object(MixMateusScraper, "_fetch_with_retry", side_effect=get), \
                patch.object(MixMateusScraper, "fetch_encartes", lambda self: today_only(self, now=TODAY)):
            offers = self.scraper.scrape()
        self.assertEqual([(o.product_name, o.price, o.store_name) for o in offers], [("Arroz Camil Branco Tipo 1", 4.59, "Mix Mateus")])
        self.assertEqual(offers[0].offer, "Encarte até 15/11")  # the cheaper one is the Itambé flyer's
        self.assertTrue(offers[0].url.startswith("https://ofertasmateus.com/api-proxy.php?file="))

    def test_a_flyer_that_cannot_be_read_does_not_lose_the_others(self):
        calls = []

        def get(method, url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                raise RuntimeError("timed out")
            return pdf_response(product(60, 300, ["Arroz Camil"], "4", "99"))

        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()), \
                patch.object(MixMateusScraper, "_fetch_with_retry", side_effect=get):
            with self.assertLogs("scraper.sites.mix_mateus", level="WARNING"):
                offers = self.scraper.scrape()
        self.assertEqual([o.price for o in offers], [4.99])

    def test_without_pdfplumber_no_prices_are_read_but_nothing_breaks(self):
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()), \
                patch.object(MixMateusScraper, "_fetch_with_retry", return_value=SimpleNamespace(content=b"")), \
                patch.object(flyer_pdf, "read_offers", side_effect=ImportError("pdfplumber")):
            with self.assertLogs("scraper.sites.mix_mateus", level="WARNING"):
                self.assertEqual(self.scraper.scrape(), [])

    def test_branches_are_only_mix_mateus_stores_with_a_street_address_a_geocoder_can_use(self):
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()):
            branches = {b.name: b for b in self.scraper.fetch_locations()}
        self.assertNotIn("Crateús", " ".join(branches))  # Mateus Supermercados (brand SM), not Mix
        self.assertEqual(sorted(branches), ["Caucaia", "Henrique Jorge", "José Walter", "Messejana", "Sobral"])
        self.assertEqual(branches["José Walter"].address, "Avenida Presidente Costa e Silva, 2646, José Walter, Fortaleza, CE")
        self.assertEqual(branches["Henrique Jorge"].address, "Henrique Jorge - Av. Senador Fernandes Távora, 2100, Fortaleza, CE")
        # "Brasil" goes, and the postcode of a highway address (a geocoder found neither with them); a street's postcode
        # stays: without it Sobral's street was found in Fortaleza
        self.assertEqual(branches["Messejana"].address, "BR-116, 9800 - Messejana, Fortaleza - CE")
        self.assertEqual((branches["Messejana"].lat, branches["Messejana"].lon), (None, None))  # geocoded afterward
        self.assertEqual(branches["Messejana"].external_id, "mix-messejana")

    def test_a_city_that_fails_does_not_lose_the_other_cities_branches(self):
        base = fake_api()

        def flaky(url, params=None):
            if params["endpoint"] == "/cidades/caucaia/lojas":
                raise RuntimeError("down")
            return base(url, params)

        with patch.object(MixMateusScraper, "fetch_raw", side_effect=flaky):
            with self.assertLogs("scraper.sites.mix_mateus", level="WARNING"):
                names = {b.name for b in self.scraper.fetch_locations()}
        self.assertIn("Messejana", names)
        self.assertNotIn("Caucaia", names)

    def test_the_flyer_reaches_the_snapshot_as_a_pdf_with_its_end(self):
        with patch.object(MixMateusScraper, "fetch_raw", side_effect=fake_api()):
            encartes = self.scraper.fetch_encartes(now=TODAY)
        store = SimpleNamespace(id=9, name="Mix Mateus")
        flyers = {f["title"]: f for f in _image_flyers({"Mix Mateus": store}, "Mix Mateus", "https://ofertasmateus.com", encartes, "now")}
        regular = flyers["Regular"]
        self.assertEqual((regular["media_type"], regular["media_pages"]), ("pdf", []))
        self.assertTrue(regular["media_url"].endswith("1793620425_6ae879c9d21e2.pdf"))
        self.assertEqual((regular["valid_from"], regular["valid_until"]), ("2026-11-01T18:00:00-03:00", "2026-11-05T23:59:00-03:00"))
        self.assertEqual(regular["id"], "mix-mateus-20763")


if __name__ == "__main__":
    unittest.main()
