"""Tests for the address search behind the UI's "Perto de você" filter."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from services import address_search
from services.address_search import AddressSearchError, geocode_address, reverse_address, search_addresses

PHOTON = {"features": [
    {"geometry": {"type": "Point", "coordinates": [-38.5021, -3.7247]},
     "properties": {"osm_type": "W", "osm_id": 1, "name": "Atlantis Beira-Mar", "street": "Avenida Beira Mar",
                    "housenumber": "2120", "district": "Meireles", "city": "Fortaleza"}},
    {"geometry": {"type": "Point", "coordinates": [-38.5104, -3.7206]},
     "properties": {"osm_type": "W", "osm_id": 2, "name": "Avenida Beira Mar", "district": "Meireles", "city": "Fortaleza"}},
    {"geometry": {"type": "Point", "coordinates": [-38.5047, -3.7232]},  # same label as the one before
     "properties": {"osm_type": "W", "osm_id": 3, "name": "Avenida Beira Mar", "district": "Meireles", "city": "Fortaleza"}},
    {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, "properties": {"osm_id": 4, "name": "Rota"}},
    {"geometry": {"type": "Point", "coordinates": [-38.5, -3.7]}, "properties": {"name": "Sem id"}},
]}


def reply(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class TestSearchAddresses(unittest.TestCase):
    def setUp(self):
        address_search._cache.clear()

    @patch("services.address_search.requests.get")
    def test_places_have_a_label_and_coordinates(self, mock_get):
        mock_get.return_value = reply(PHOTON)
        places = search_addresses("  Av. Beira   Mar ")
        self.assertEqual(places[0], {"id": "W1", "label": "Atlantis Beira-Mar · Avenida Beira Mar, 2120 · Meireles · Fortaleza",
                                     "latitude": -3.7247, "longitude": -38.5021})
        self.assertEqual([p["id"] for p in places], ["W1", "W2"])  # duplicate label, non-point and id-less results dropped

    @patch("services.address_search.requests.get")
    def test_search_is_limited_to_fortaleza(self, mock_get):
        mock_get.return_value = reply(PHOTON)
        search_addresses("beira mar")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["q"], "beira mar")
        self.assertEqual(params["bbox"], "-38.65,-3.95,-38.35,-3.65")
        self.assertIn("User-Agent", mock_get.call_args.kwargs["headers"])
        self.assertLessEqual(mock_get.call_args.kwargs["timeout"], 10)

    @patch("services.address_search.requests.get")
    def test_repeated_searches_use_the_cache_ignoring_case_and_spacing(self, mock_get):
        mock_get.return_value = reply(PHOTON)
        search_addresses("Beira Mar")
        search_addresses("  beira   MAR")
        self.assertEqual(mock_get.call_count, 1)

    @patch("services.address_search.requests.get", side_effect=requests.Timeout("slow"))
    def test_service_failure_raises_and_is_not_cached(self, _):
        with self.assertRaises(AddressSearchError):
            search_addresses("beira mar")
        self.assertEqual(len(address_search._cache), 0)

    @patch("services.address_search.requests.get")
    def test_invalid_json_is_a_service_failure(self, mock_get):
        response = reply(None)
        response.json.side_effect = ValueError("not json")
        mock_get.return_value = response
        with self.assertRaises(AddressSearchError):
            search_addresses("beira mar")

    @patch("services.address_search.requests.get")
    def test_cache_is_bounded(self, mock_get):
        mock_get.return_value = reply({"features": []})
        for n in range(address_search.CACHE_MAX_ENTRIES + 5):
            search_addresses(f"rua {n}")
        self.assertEqual(len(address_search._cache), address_search.CACHE_MAX_ENTRIES)


class TestLocationRoute(unittest.TestCase):
    def post(self, body):
        from web.app import app

        return app.test_client().post("/api/location", json=body)

    def test_returns_places(self):
        places = [{"id": "W1", "label": "Rua A", "latitude": -3.7, "longitude": -38.5}]
        with patch("web.app.search_addresses", return_value=places) as mock_search:
            resp = self.post({"query": " Rua   A "})
        self.assertEqual((resp.status_code, resp.get_json()), (200, {"places": places}))
        mock_search.assert_called_once_with("Rua A")

    def test_rejects_short_long_and_missing_queries(self):
        for body in ({"query": "ab"}, {"query": "x" * 121}, {}, {"query": None}):
            with patch("web.app.search_addresses") as mock_search:
                resp = self.post(body)
            self.assertEqual(resp.status_code, 400, body)
            self.assertIn("error", resp.get_json())
            mock_search.assert_not_called()

    def test_service_outage_is_a_502_with_a_message(self):
        with patch("web.app.search_addresses", side_effect=AddressSearchError("down")):
            resp = self.post({"query": "beira mar"})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("indisponível", resp.get_json()["error"])


OLIVEIRA_PAIVA = {"geometry": {"type": "Point", "coordinates": [-38.5032, -3.7994]},
                  "properties": {"osm_type": "W", "osm_id": 9, "name": "Oliveira Paiva",
                                 "street": "Avenida Oliveira Paiva", "city": "Fortaleza"}}
AQUIRAZ_CENTRE = {"geometry": {"type": "Point", "coordinates": [-38.39, -3.90]},
                  "properties": {"osm_type": "N", "osm_id": 10, "name": "Aquiraz", "city": "Aquiraz"}}
# A real failure mode: "Nossa Sra. de Lurdes" with no city matched a street in Portugal instead of Ceará.
PORTUGAL_MISMATCH = {"geometry": {"type": "Point", "coordinates": [-8.485993, 40.6137435]},
                     "properties": {"osm_type": "W", "osm_id": 11, "name": "Nossa Sra. de Lurdes", "city": "Porto"}}


class TestGeocodeAddress(unittest.TestCase):
    @patch("services.address_search.requests.get")
    def test_a_plain_address_resolves_on_the_first_try(self, mock_get):
        mock_get.return_value = reply({"features": [OLIVEIRA_PAIVA]})
        place = geocode_address("OLIVEIRA PAIVA, 170, C DOS FUNCIONARIOS, Fortaleza, CE")
        self.assertEqual((place["latitude"], place["longitude"]), (-3.7994, -38.5032))
        self.assertEqual(mock_get.call_count, 1)

    @patch("services.address_search.requests.get")
    def test_store_complement_noise_is_stripped_before_the_second_try(self, mock_get):
        # "LOJA 01" and "S/N" resolve nothing on their own but must not block the rest of the address.
        mock_get.side_effect = [reply({"features": []}), reply({"features": [OLIVEIRA_PAIVA]})]
        place = geocode_address("OLIVEIRA PAIVA, S/N, LOJA 01, Fortaleza, CE")
        self.assertIsNotNone(place)
        self.assertEqual(mock_get.call_count, 2)
        self.assertNotIn("LOJA", mock_get.call_args.kwargs["params"]["q"])
        self.assertNotIn("S/N", mock_get.call_args.kwargs["params"]["q"].upper().replace(" ", ""))

    @patch("services.address_search.requests.get")
    def test_falls_back_to_city_and_state_as_a_last_resort(self, mock_get):
        mock_get.side_effect = [reply({"features": []}), reply({"features": []}), reply({"features": [AQUIRAZ_CENTRE]})]
        place = geocode_address("RODOVIA CE-040, 1980, KM 19 LOJA 11, Jacundá, Aquiraz, CE")
        self.assertIsNotNone(place)
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_get.call_args.kwargs["params"]["q"], "Aquiraz, CE")

    @patch("services.address_search.requests.get")
    def test_none_when_every_attempt_fails(self, mock_get):
        mock_get.return_value = reply({"features": []})
        self.assertIsNone(geocode_address("Endereço inexistente, S/N, LOJA 1, Nada, CE"))

    def test_blank_address_is_not_even_attempted(self):
        with patch("services.address_search.requests.get") as mock_get:
            self.assertIsNone(geocode_address("   "))
        mock_get.assert_not_called()

    @patch("services.address_search.requests.get")
    def test_only_the_first_attempt_is_biased_toward_fortaleza(self, mock_get):
        mock_get.side_effect = [reply({"features": []}), reply({"features": [OLIVEIRA_PAIVA]})]
        geocode_address("Rua sem numero, S/N, Alguma Cidade, CE")
        first, second = (c.kwargs["params"] for c in mock_get.call_args_list)
        self.assertIn("lat", first)
        self.assertNotIn("lat", second)

    @patch("services.address_search.requests.get", side_effect=requests.Timeout("slow"))
    def test_service_failure_raises(self, _):
        with self.assertRaises(AddressSearchError):
            geocode_address("Alguma Rua, Fortaleza, CE")

    @patch("services.address_search.requests.get")
    def test_a_match_thousands_of_km_away_is_rejected_not_returned(self, mock_get):
        # A same-named street matched in Portugal instead of Ceará: worse than no match at all.
        mock_get.return_value = reply({"features": [PORTUGAL_MISMATCH]})
        self.assertIsNone(geocode_address("Av. Nossa Sra. de Lurdes, 77 - Centro"))

    @patch("services.address_search.requests.get")
    def test_a_distant_mismatch_on_one_attempt_still_lets_a_later_attempt_succeed(self, mock_get):
        mock_get.side_effect = [reply({"features": [PORTUGAL_MISMATCH]}), reply({"features": [AQUIRAZ_CENTRE]})]
        place = geocode_address("Av. Nossa Sra. de Lurdes, 77 - Centro, Aquiraz, CE")
        self.assertEqual(place["label"].split(" · ")[0], "Aquiraz")


class TestReverseAddress(unittest.TestCase):
    @patch("services.address_search.requests.get")
    def test_returns_the_address_and_rounds_the_position(self, mock_get):
        mock_get.return_value = reply({"features": [PHOTON["features"][0]]})
        found = reverse_address(-3.724689123, -38.502151999)
        self.assertEqual(found["label"], "Atlantis Beira-Mar · Avenida Beira Mar, 2120 · Meireles · Fortaleza")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual((params["lat"], params["lon"]), ("-3.7247", "-38.5022"))
        self.assertTrue(mock_get.call_args.args[0].endswith("/reverse"))

    @patch("services.address_search.requests.get")
    def test_none_when_there_is_no_address(self, mock_get):
        mock_get.return_value = reply({"features": []})
        self.assertIsNone(reverse_address(0.0, 0.0))

    @patch("services.address_search.requests.get", side_effect=requests.Timeout("slow"))
    def test_service_failure_raises(self, _):
        with self.assertRaises(AddressSearchError):
            reverse_address(-3.7, -38.5)


class TestReverseRoute(unittest.TestCase):
    def get(self, query):
        from web.app import app

        return app.test_client().get(f"/api/location/reverse?{query}")

    def test_returns_the_place(self):
        place = {"id": "W1", "label": "Rua A · Fortaleza", "latitude": -3.7, "longitude": -38.5}
        with patch("web.app.reverse_address", return_value=place) as mock_reverse:
            resp = self.get("lat=-3.7&lon=-38.5")
        self.assertEqual((resp.status_code, resp.get_json()), (200, {"place": place}))
        mock_reverse.assert_called_once_with(-3.7, -38.5)

    def test_rejects_invalid_coordinates(self):
        for query in ("", "lat=abc&lon=1", "lat=91&lon=0", "lat=0&lon=181", "lat=-3.7", "lat=nan&lon=0"):
            with patch("web.app.reverse_address") as mock_reverse:
                self.assertEqual(self.get(query).status_code, 400, query)
            mock_reverse.assert_not_called()

    def test_service_outage_is_a_502(self):
        with patch("web.app.reverse_address", side_effect=AddressSearchError("down")):
            self.assertEqual(self.get("lat=-3.7&lon=-38.5").status_code, 502)


class TestSessionPlaceholder(unittest.TestCase):
    def test_answers_match_the_old_stub(self):
        from web.app import app

        client = app.test_client()
        self.assertEqual(client.get("/api/session").get_json(), {"actor": None})
        self.assertEqual(client.delete("/api/session").get_json(), {"ok": True})
        self.assertEqual(client.post("/api/session").status_code, 501)


if __name__ == "__main__":
    unittest.main()
