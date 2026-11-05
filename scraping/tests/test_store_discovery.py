"""Store discovery: fuzzy chain names, known chains left out, candidates grouped and saved."""

import os
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"

from models import CandidateChain, SessionLocal, Store, init_db  # noqa: E402
from services import store_discovery as sd  # noqa: E402


def element(name, lat=-3.7, lon=-38.5, **tags):
    return {"type": "node", "lat": lat, "lon": lon, "tags": {"name": name, "shop": "supermarket", **tags}}


class TestKeys(unittest.TestCase):
    def test_accents_case_noise_words_and_branch_suffixes_are_dropped(self):
        for name in ("Supermercado Guará", "SUPER GUARÁ", "Guará Supermercados - Loja Aldeota", "Guará (Messejana)"):
            self.assertEqual(sd.key_of(name), "guara")

    def test_an_apostrophe_does_not_split_a_name(self):
        self.assertEqual(sd.key_of("Sam's Club"), sd.key_of("Sams Club"))

    def test_atacadao_is_a_name_not_noise(self):
        self.assertEqual(sd.key_of("Atacadão"), "atacadao")
        self.assertEqual(sd.key_of("Assaí Atacadista"), "assai")

    def test_a_name_made_only_of_noise_has_no_key(self):
        self.assertEqual(sd.key_of("Supermercado"), "")

    def test_same_chain_accepts_extra_words_and_typos_but_not_a_different_chain(self):
        self.assertTrue(sd.same_chain("atacadao", "atacadao lag"))
        self.assertTrue(sd.same_chain("frangolandia", "frangolandai"))
        self.assertFalse(sd.same_chain("sao luiz", "sao francisco"))
        self.assertFalse(sd.same_chain("", "cometa"))


class TestCandidates(unittest.TestCase):
    def places(self, *names):
        return sd.to_places([element(n) for n in names])[0]

    def test_a_chain_we_have_is_left_out_whatever_its_spelling(self):
        known = sd.known_keys(["Mercadinho São Luiz", "Cometa", "Sams Club"])
        places = self.places("Mercadão São Luiz", "Supermercado Cometa", "Sam's Club", "Super Lagoa")
        groups = sd.candidates(places, known)
        self.assertEqual([[p.name for p in g] for g in groups], [["Super Lagoa"]])

    def test_spellings_of_an_unknown_chain_are_one_group_the_biggest_first(self):
        places = self.places("Super Lagoa", "Supermercado Lagoa", "Lagoa", "Assaí Atacadista", "Super do Povo",
                             "Super do Povo (José Walter)", "Super do Povo Pátio Arvoredo")
        groups = sd.candidates(places, [])
        self.assertEqual([len(g) for g in groups], [3, 3, 1])
        self.assertEqual({p.key for p in groups[0]} | {p.key for p in groups[1]}, {"lagoa", "povo", "povo patio arvoredo"})

    def test_places_without_a_name_are_counted_not_listed(self):
        places, unnamed = sd.to_places([element("Super Lagoa"), {"type": "node", "lat": 1, "lon": 2, "tags": {"shop": "supermarket"}},
                                        element("Supermercado")])
        self.assertEqual((len(places), unnamed), (1, 2))

    def test_a_way_uses_its_centre_and_the_brand_wins_over_the_name(self):
        way = {"type": "way", "center": {"lat": -3.8, "lon": -38.6}, "tags": {"name": "Loja 12", "brand": "Mix Mateus"}}
        place = sd.to_places([way])[0][0]
        self.assertEqual((place.key, place.lat, place.lon), ("mix mateus", -3.8, -38.6))


class TestQuery(unittest.TestCase):
    def test_names_and_state_are_checked_before_they_go_into_the_query(self):
        with self.assertRaises(ValueError):
            sd.overpass_query("CE", ['Fortaleza"];out;'], False)
        with self.assertRaises(ValueError):
            sd.overpass_query("ce;", ["Fortaleza"], False)
        self.assertIn("BR-PE", sd.overpass_query("PE", ["Recife", "Olinda"], False))
        self.assertIn("convenience", sd.overpass_query("PE", ["Recife"], True))
        self.assertNotIn("convenience", sd.overpass_query("PE", ["Recife"], False))


class TestSave(unittest.TestCase):
    def setUp(self):
        init_db()
        with SessionLocal() as s:
            s.query(CandidateChain).delete()
            s.query(Store).delete()
            s.add(Store(name="Cometa"))
            s.commit()

    def run_with(self, elements, **kwargs):
        lines = []
        with patch.object(sd, "fetch_elements", return_value=elements):
            sd.run("CE", ["Fortaleza"], out=lines.append, **kwargs)
        return lines

    def test_candidates_are_saved_and_flagged_new_once_then_kept_with_their_status(self):
        elements = [element("Super Lagoa", addr_street="Rua A"), element("Supermercado Lagoa"), element("Cometa"),
                    element("Assaí Atacadista")]
        first = self.run_with(elements)
        self.assertIn("2 candidate chain(s)", first[0])
        self.assertTrue(all(line.endswith("NEW") for line in first[2:]))
        with SessionLocal() as s:
            lagoa = s.query(CandidateChain).filter_by(key="lagoa").one()
            self.assertEqual((lagoa.branches, lagoa.status, lagoa.state), (2, "new", "CE"))
            lagoa.status = "ignored"
            s.commit()
        second = self.run_with(elements + [element("Lagoa Supermercados")])
        self.assertFalse(any("NEW" in line for line in second[2:]))
        self.assertFalse(any("Lagoa" in line for line in second[2:]))  # ignored: not listed any more
        with SessionLocal() as s:
            lagoa = s.query(CandidateChain).filter_by(key="lagoa").one()
            self.assertEqual((lagoa.branches, lagoa.status), (3, "ignored"))

    def test_a_dry_run_saves_nothing(self):
        self.run_with([element("Super Lagoa")], dry_run=True)
        with SessionLocal() as s:
            self.assertEqual(s.query(CandidateChain).count(), 0)


if __name__ == "__main__":
    unittest.main()
