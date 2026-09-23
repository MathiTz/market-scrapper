"""Tests for services.store_locations: keeping real branch addresses in step with each chain's own site."""

import unittest
from unittest.mock import patch

from models import SessionLocal, Store, StoreLocation, init_db
from scraper.base import BranchLocation
from scraper.sites.atacadao import AtacadaoScraper
from scraper.sites.mercadinho import MercadinhoScraper
from services.store_locations import sync_store_locations

PORTO_DAS_DUNAS = BranchLocation(
    external_id="1621", name="Porto das Dunas",
    address="Av. Caminho do Sol, S/N, LOJA 01, Porto das Dunas, Aquiraz, CE",
)
OLIVEIRA_PAIVA = BranchLocation(
    external_id="355", name="Oliveira Paiva", address="OLIVEIRA PAIVA, 170, C DOS FUNCIONARIOS, Fortaleza, CE",
)
ATACADAO_FATIMA = BranchLocation(
    external_id="a1", name="Atacadão - FORTALEZA FATIMA",
    address="Avenida Luciano Carneiro, S/N, Parreão, Fortaleza, CE", lat=-3.758612, lon=-38.534733,
)


class TestSyncStoreLocations(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()
        self.addCleanup(self.tear_down)

    def tear_down(self):
        self.db.query(StoreLocation).delete()
        self.db.query(Store).filter(Store.name.in_(["Mercadinho São Luiz", "Atacadão"])).delete()
        self.db.commit()
        self.db.close()

    def branches(self, store_name):
        store = self.db.query(Store).filter(Store.name == store_name).first()
        if store is None:
            return []
        return self.db.query(StoreLocation).filter(StoreLocation.store_id == store.id).all()

    def test_a_branch_with_only_a_text_address_is_geocoded_and_saved(self):
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[PORTO_DAS_DUNAS]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.833, "longitude": -38.380}):
            result = sync_store_locations(site_key="mercadinho")
        self.assertEqual(result, {"mercadinho": 1})
        saved = self.branches("Mercadinho São Luiz")
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0].name, saved[0].lat, saved[0].lon), ("Porto das Dunas", -3.833, -38.380))

    def test_a_branch_with_its_own_coordinates_is_not_geocoded(self):
        with patch.object(AtacadaoScraper, "fetch_locations", return_value=[ATACADAO_FATIMA]), \
                patch("services.store_locations.geocode_address") as geocode:
            sync_store_locations(site_key="atacadao")
        geocode.assert_not_called()
        self.assertEqual(self.branches("Atacadão")[0].lat, -3.758612)

    def test_a_branch_that_cannot_be_geocoded_is_skipped_not_saved_half_done(self):
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[PORTO_DAS_DUNAS, OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", side_effect=[None, {"latitude": -3.73, "longitude": -38.49}]):
            result = sync_store_locations(site_key="mercadinho")
        self.assertEqual(result, {"mercadinho": 1})
        self.assertEqual([b.name for b in self.branches("Mercadinho São Luiz")], ["Oliveira Paiva"])

    def test_running_twice_updates_the_same_row_rather_than_duplicating_it(self):
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            sync_store_locations(site_key="mercadinho")
        moved = BranchLocation(external_id="355", name="Oliveira Paiva (Reformada)", address=OLIVEIRA_PAIVA.address)
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[moved]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.731, "longitude": -38.491}):
            sync_store_locations(site_key="mercadinho")
        saved = self.branches("Mercadinho São Luiz")
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0].name, saved[0].lat), ("Oliveira Paiva (Reformada)", -3.731))

    def test_a_branch_missing_from_a_full_run_is_removed(self):
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[PORTO_DAS_DUNAS, OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            sync_store_locations(site_key="mercadinho")
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            sync_store_locations(site_key="mercadinho")
        self.assertEqual([b.name for b in self.branches("Mercadinho São Luiz")], ["Oliveira Paiva"])

    def test_a_run_finding_under_half_the_known_branches_keeps_the_rest_instead_of_deleting_them(self):
        many = [BranchLocation(external_id=str(i), name=f"Branch {i}", address="x") for i in range(4)]
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=many), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            sync_store_locations(site_key="mercadinho")
        # A short run only captures one of the four: below the 50% bar, so the other three must stay.
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[many[0]]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            result = sync_store_locations(site_key="mercadinho")
        self.assertEqual(result, {"mercadinho": 1})  # what was found is still recorded as saved
        self.assertEqual(len(self.branches("Mercadinho São Luiz")), 4)  # nothing removed

    def test_a_scraper_without_fetch_locations_is_skipped_not_an_error(self):
        # Every real chain has fetch_locations now, so this fakes one that does not, to keep covering the
        # branch for whenever a new chain without a known source is next onboarded.
        class _NoLocations:
            site_key = "no-locations-test"
            site_name = "No Locations Chain"

        with patch.dict("services.store_locations.SCRAPER_MAP", {"no-locations-test": _NoLocations}):
            result = sync_store_locations(site_key="no-locations-test")
        self.assertEqual(result, {})

    def test_a_failed_fetch_is_skipped_and_does_not_stop_the_others(self):
        # sync_store_locations() with no site_key runs every scraper that HAS fetch_locations for real
        # (a live Selenium browser launch, or a real HTTP call, per chain) unless each one is mocked here -
        # found by introspection, so a newly-onboarded chain cannot slip through unmocked the way Pinheiro
        # once did when this test still named the scrapers by hand.
        from scraper.sites import ALL_SCRAPERS

        others = [cls for cls in ALL_SCRAPERS if cls is not MercadinhoScraper and cls is not AtacadaoScraper
                  and hasattr(cls, "fetch_locations")]
        patchers = [patch.object(cls, "fetch_locations", return_value=[]) for cls in others]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

        with patch.object(MercadinhoScraper, "fetch_locations", side_effect=RuntimeError("no chromedriver")), \
                patch.object(AtacadaoScraper, "fetch_locations", return_value=[ATACADAO_FATIMA]):
            result = sync_store_locations()
        self.assertNotIn("mercadinho", result)
        self.assertEqual(result.get("atacadao"), 1)

    def test_attaches_to_the_lowest_id_store_when_the_name_is_duplicated(self):
        # stores holds duplicates from the seed script having run more than once (see services/public_api.py's
        # "canonical" retailer); a branch must attach to the same row the public API resolves the chain to.
        first = Store(name="Mercadinho São Luiz")
        self.db.add(first)
        self.db.commit()
        dup = Store(name="Mercadinho São Luiz")
        self.db.add(dup)
        self.db.commit()
        self.assertLess(first.id, dup.id)
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", return_value={"latitude": -3.73, "longitude": -38.49}):
            sync_store_locations(site_key="mercadinho")
        saved = self.db.query(StoreLocation).filter(StoreLocation.external_id == "355").one()
        self.assertEqual(saved.store_id, first.id)

    def test_a_geocoding_failure_retries_with_the_branch_name_as_a_city_hint(self):
        # A real case: Pinheiro's "Acaraú" branch address has no city in it at all.
        no_city = BranchLocation(external_id="acarau", name="Acaraú", address="Rua Coronel Sales, 175 - Curral Velho")
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[no_city]), \
                patch("services.store_locations.geocode_address",
                      side_effect=[None, {"latitude": -2.88, "longitude": -40.12}]) as geocode:
            result = sync_store_locations(site_key="mercadinho")
        self.assertEqual(result, {"mercadinho": 1})
        self.assertEqual(geocode.call_count, 2)
        self.assertIn("Acaraú, CE", geocode.call_args_list[1].args[0])
        self.assertEqual(self.branches("Mercadinho São Luiz")[0].lat, -2.88)

    def test_no_retry_when_the_branch_name_is_already_in_the_address(self):
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[OLIVEIRA_PAIVA]), \
                patch("services.store_locations.geocode_address", return_value=None) as geocode:
            sync_store_locations(site_key="mercadinho")
        geocode.assert_called_once()  # "Oliveira Paiva" is already in the address; retrying would be redundant

    def test_still_nothing_saved_when_the_hint_retry_also_fails(self):
        no_city = BranchLocation(external_id="acarau", name="Acaraú", address="Rua Coronel Sales, 175 - Curral Velho")
        with patch.object(MercadinhoScraper, "fetch_locations", return_value=[no_city]), \
                patch("services.store_locations.geocode_address", return_value=None):
            result = sync_store_locations(site_key="mercadinho")
        self.assertEqual(result, {"mercadinho": 0})
        self.assertEqual(self.branches("Mercadinho São Luiz"), [])

    def test_unknown_site_key_raises(self):
        with self.assertRaises(ValueError):
            sync_store_locations(site_key="not-a-real-chain")


if __name__ == "__main__":
    unittest.main()
