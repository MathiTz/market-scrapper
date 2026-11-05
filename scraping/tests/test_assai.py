"""Assaí: the flyers file and the stores page, both read through the browser (the site is behind a JS challenge)."""

import html
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

os.environ["DATABASE_URL"] = "sqlite://"

from scraper.sites import FLYER_ONLY_SCRAPERS, SCRAPER_MAP  # noqa: E402
from scraper.sites.assai import AssaiScraper  # noqa: E402
from services.public_api import _image_flyers  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
OFFERS = (FIXTURES / "assai_ofertas.json").read_text(encoding="utf-8")
STORES = (FIXTURES / "assai_stores.html").read_text(encoding="utf-8")
TODAY = datetime(2026, 11, 5, 12, 0)


def as_page(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup, "lxml")


def json_page(text: str) -> BeautifulSoup:
    return as_page(f"<html><body><pre>{html.escape(text)}</pre></body></html>")  # how the browser shows a JSON file


class TestAssai(unittest.TestCase):
    def setUp(self):
        self.scraper = AssaiScraper()

    def test_it_publishes_no_prices_and_is_not_scraped_for_offers(self):
        self.assertEqual(self.scraper.scrape(), [])
        self.assertIn(AssaiScraper, FLYER_ONLY_SCRAPERS)
        self.assertNotIn("assai", SCRAPER_MAP)  # the release's scrape loop would find it empty

    def test_a_flyer_carries_its_pages_its_dates_and_who_it_is_for(self):
        with patch.object(AssaiScraper, "render", return_value=json_page(OFFERS)):
            flyers = {e.id: e for e in self.scraper.fetch_encartes(now=TODAY)}
        everyone = flyers["175264-544"]
        self.assertEqual((everyone.posted_at, everyone.valid_until), ("2026-11-02T00:00:00", "2026-11-08T23:59:59"))
        self.assertEqual(everyone.description, "Todas as lojas do Ceará")
        self.assertEqual(len(flyers["175265-579"].pages), 2)
        self.assertEqual(flyers["175265-579"].cover_url, flyers["175265-579"].pages[0])
        # the file lists three Ceará stores; a flyer for most of them names who is left out, for few who is in
        self.assertEqual(flyers["175265-579"].description, "Todas as lojas do Ceará, exceto: Iguatu")
        self.assertEqual(flyers["175450-582"].description, "Lojas: Iguatu")

    def test_an_ended_flyer_and_one_for_another_state_are_left_out(self):
        with patch.object(AssaiScraper, "render", return_value=json_page(OFFERS)):
            ids = {e.id for e in self.scraper.fetch_encartes(now=TODAY)}
            self.assertNotIn("170000-1", ids)  # ended on 08/10
            self.assertNotIn("170001-2", ids)  # none of its stores is in Ceará
            self.assertIn("170000-1", {e.id for e in self.scraper.fetch_encartes(now=datetime(2026, 10, 6))})

    def test_a_file_without_the_states_stores_is_an_error_not_an_empty_list(self):
        with patch.object(AssaiScraper, "render", return_value=json_page('{"ofertas": [], "lojas": []}')):
            with self.assertRaises(RuntimeError):
                self.scraper.fetch_encartes(now=TODAY)

    def test_imperva_challenge_page_is_reported_as_such_not_as_a_json_error(self):
        challenge = '<html><body><iframe id="main-iframe" src="/_Incapsula_Resource?SWUDNSAI=31"></iframe></body></html>'
        with patch.object(AssaiScraper, "render", return_value=as_page(challenge)):
            with self.assertRaisesRegex(RuntimeError, "Imperva"):
                self.scraper.fetch_encartes(now=TODAY)

    def test_the_flyer_reaches_the_snapshot_with_its_end_and_who_it_is_for(self):
        with patch.object(AssaiScraper, "render", return_value=json_page(OFFERS)):
            encartes = self.scraper.fetch_encartes(now=TODAY)
        store = type("Store", (), {"id": 7, "name": "Assaí Atacadista"})()
        flyer = next(f for f in _image_flyers({"Assaí Atacadista": store}, "Assaí Atacadista",
                                              "https://www.assai.com.br/ofertas", encartes, "now")
                     if f["version_hash"] == "175264-544")
        self.assertEqual(flyer["id"], "assaí-atacadista-175264-544")
        self.assertEqual((flyer["valid_from"], flyer["valid_until"]), ("2026-11-02T00:00:00-03:00", "2026-11-08T23:59:59-03:00"))
        self.assertEqual((flyer["scope"], flyer["retailer_id"]), ("Todas as lojas do Ceará", "7"))

    def test_branches_come_with_real_coordinates_from_the_embedded_store_list(self):
        with patch.object(AssaiScraper, "render", return_value=as_page(STORES)):
            branches = {b.name: b for b in self.scraper.fetch_locations()}
        self.assertNotIn("Araraquara", branches)  # São Paulo: the scraper keeps to Ceará
        bezerra = branches["Bezerra M (Fortaleza)"]
        self.assertEqual((bezerra.external_id, bezerra.lat, bezerra.lon), ("23", -3.731521, -38.541325))
        self.assertEqual(bezerra.address, "Avenida Bezerra de Menezes, 571, Farias de Brito, Fortaleza, CE")
        self.assertEqual(branches["Tapioqueiras"].address, "Av Washington Soares, 10300, Messejana, Fortaleza, CE")  # no ",,"

    def test_coordinates_in_another_state_or_missing_are_dropped_so_the_address_is_geocoded(self):
        with patch.object(AssaiScraper, "render", return_value=as_page(STORES)):
            with self.assertLogs("scraper.sites.assai", level="WARNING"):
                branches = {b.name: b for b in self.scraper.fetch_locations()}
        for name in ("Iguatu", "Montese"):  # Iguatu's point is in Mato Grosso do Sul; Montese has none
            self.assertEqual((branches[name].lat, branches[name].lon), (None, None), name)
            self.assertIn("CE", branches[name].address)

    def test_a_challenge_page_instead_of_the_stores_gives_no_branches(self):
        with patch.object(AssaiScraper, "render", return_value=as_page("<html><body>Pardon Our Interruption</body></html>")):
            with self.assertLogs("scraper.sites.assai", level="WARNING"):
                self.assertEqual(self.scraper.fetch_locations(), [])


if __name__ == "__main__":
    unittest.main()
