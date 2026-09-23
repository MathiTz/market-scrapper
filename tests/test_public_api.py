"""Tests for the /api/public payload consumed by the Mercado em Dia UI."""

import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"  # never touch the real market.db

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models import Base, Price, Product, ScrapeAttempt, Store, StoreLocation  # noqa: E402
from scraper.sites.cometa import Encarte  # noqa: E402
from services.public_api import (  # noqa: E402
    build_public, categorize, match_products, match_tokens, parse_size, parse_validity,
)


class TestDerivedFields(unittest.TestCase):
    def test_parse_size(self):
        for name, expected in [
            ("Cerveja Lager Heineken Lata 269ml", (269, "ml", 1)),
            ("Peito De Frango Resfriado 1,2kg", (1200, "g", 1)),
            ("Água Sanitária Ypê Frasco 2l", (2000, "ml", 1)),
            ("Papel Higiênico Neve 20m Pacote 12 Unidades", (1, "un", 12)),
            ("Pack Lava-louças Ypê 6 Unidades 500ml Cada", (500, "ml", 6)),
            ("Banana nanica", (1, "un", 1)),
        ]:
            self.assertEqual(parse_size(name), expected, name)

    def test_parse_size_of_fresh_meat_and_produce_sold_by_weight(self):
        # Real cases: no fixed pack size is named because there isn't one - the cut or bunch weighs
        # whatever it weighs, and the price the scraper captured already *is* the per-kilo price.
        for name, expected in [
            ("Maminha Bovina Fribal Bandeja Kg", (1000, "g", 1)),
            ("Abacate Kg", (1000, "g", 1)),
            ("Batata Doce Quilo", (1000, "g", 1)),
            ("Carne Bovina Acém Porc Friboi Resf Preço por quilo na peça", (1000, "g", 1)),
            # An explicit weight still wins over the bare word ("Kg" here is just part of "1,5kg").
            ("Picanha Bovina Uruguaia Congelada 1,5kg", (1500, "g", 1)),
        ]:
            self.assertEqual(parse_size(name), expected, name)

    def test_categorize(self):
        for name, expected in [
            ("Água Sanitária Ypê Frasco 2l", "Limpeza"),      # not Bebidas
            ("Pack Lava-louças Ypê 6 Unidades", "Limpeza"),
            ("Creme de Leite UHT Nestlé 200g", "Laticínios e frios"),
            ("Cerveja Amstel Lata", "Bebidas"),
            ("Peito De Frango Com Osso", "Carnes e peixes"),
            ("Salmão fresco", "Carnes e peixes"),               # "sal" must not match "salmao"
            ("Produto misterioso", "Outros"),
        ]:
            self.assertEqual(categorize(name), expected, name)

    def test_parse_validity(self):
        today = date(2026, 9, 21)
        self.assertEqual(parse_validity("Ofertas válidas de 20 a 22/09 em todas as lojas", today),
                         ("2026-09-20T00:00:00-03:00", "2026-09-22T23:59:59-03:00"))
        self.assertEqual(parse_validity("válidas de 30/09 a 05/10", today),
                         ("2026-09-30T00:00:00-03:00", "2026-10-05T23:59:59-03:00"))
        self.assertEqual(parse_validity("de 28/12 a 03/01", today)[0], "2025-12-28T00:00:00-03:00")
        self.assertEqual(parse_validity("sem datas", today), (None, None))


def prods(*names):
    return [Product(id=i, name=n) for i, n in enumerate(names, start=1)]


def matched(*names):
    return [[m.name for m in ms] for ms in match_products(prods(*names)).values()]


class TestMatchProducts(unittest.TestCase):
    def test_same_product_named_differently_by_two_chains(self):
        self.assertEqual(
            matched("LASANHA SADIA BOLONHESA 600G", "Lasanha Bolonhesa Sadia Pacote 600g"),
            [["LASANHA SADIA BOLONHESA 600G", "Lasanha Bolonhesa Sadia Pacote 600g"]],
        )

    def test_packaging_and_promo_words_are_ignored(self):
        self.assertEqual(match_tokens("Leite Condensado Moça Lata 395g Grátis 15%"),
                         match_tokens("LEITE CONDENSADO MOÇA CAIXA 395G"))

    def test_different_brand_or_size_never_matches(self):
        self.assertEqual(matched("Filé de Tilápia Bomar Congelado 500g", "Filé De Tilapia Congelado Qualitá 500g"), [])
        self.assertEqual(matched("Arroz Branco Tio João 1kg", "Arroz Branco Tio João 5kg"), [])
        self.assertEqual(matched("Whisky Escocês 12 Anos 1l", "Whisky Escocês 18 Anos 1l"), [])

    def test_subset_of_words_is_not_enough(self):
        self.assertEqual(matched("Leite Condensado 395g", "Leite Condensado Moça 395g"), [])

    def test_name_without_size_joins_the_only_sized_group(self):
        self.assertEqual(
            matched("FILÉ DE PEITO DE FRANGO SADIA BANDEJA 1KG", "Filé de peito de frango SADIA"),
            [["FILÉ DE PEITO DE FRANGO SADIA BANDEJA 1KG", "Filé de peito de frango SADIA"]],
        )

    def test_name_without_size_never_bridges_two_sizes(self):
        groups = match_products(prods("Filé Frango Sadia 1kg", "Filé Frango Sadia 700g", "Filé Frango Sadia"))
        self.assertEqual(groups, {})

    def test_single_generic_word_is_never_matched(self):
        self.assertEqual(matched("Arroz 1kg", "ARROZ 1KG"), [])

    def test_group_is_keyed_by_lowest_id(self):
        groups = match_products(prods("Lasanha Sadia Bolonhesa 600g", "x y z", "Lasanha Bolonhesa Sadia 600g"))
        self.assertEqual(list(groups), [1])


class TestRetailerLocations(unittest.TestCase):
    """A chain's real, physical branches (see models/store_location.py), not the old single fake seed point."""

    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        db = self.db
        # Seed ran twice for Mercadinho too: id 1 is canonical, id 2 is the duplicate.
        db.add_all([Store(name="Mercadinho São Luiz"), Store(name="Mercadinho São Luiz"), Store(name="Cometa")])
        db.flush()
        db.add_all([
            StoreLocation(store_id=1, external_id="355", name="Oliveira Paiva",
                          address="Oliveira Paiva, 170, Fortaleza", lat=-3.73, lon=-38.49),
            StoreLocation(store_id=1, external_id="1621", name="Porto das Dunas",
                          address="Av. Caminho do Sol, Aquiraz", lat=-3.83, lon=-38.38),
            StoreLocation(store_id=2, external_id="999", name="Should not appear",
                          address="On the non-canonical duplicate row", lat=0, lon=0),
        ])
        db.commit()

    def tearDown(self):
        self.db.close()

    def test_real_branches_are_exposed_under_the_canonical_retailer_id(self):
        data = build_public(self.db, encartes=[])
        locations = {loc["name"]: loc for loc in data["retailer_locations"]}
        self.assertEqual(set(locations), {"Oliveira Paiva", "Porto das Dunas"})
        self.assertTrue(all(loc["retailer_id"] == "1" for loc in locations.values()))
        dunas = locations["Porto das Dunas"]
        self.assertEqual(dunas["address"], "Av. Caminho do Sol, Aquiraz")
        self.assertEqual((dunas["latitude"], dunas["longitude"]), (-3.83, -38.38))

    def test_a_location_on_a_duplicate_non_canonical_store_row_is_not_exposed(self):
        names = {loc["name"] for loc in build_public(self.db, encartes=[])["retailer_locations"]}
        self.assertNotIn("Should not appear", names)

    def test_a_chain_with_no_real_branches_has_none(self):
        data = build_public(self.db, encartes=[])
        self.assertEqual([loc for loc in data["retailer_locations"] if loc["retailer_id"] == "3"], [])

    def test_offers_no_longer_carry_the_old_single_fake_store_point(self):
        db = self.db
        db.add(Product(name="Arroz"))
        db.flush()
        db.add(Price(product_id=1, store_id=1, price=5.0, scraped_at=datetime.utcnow()))
        db.commit()
        offer = build_public(self.db, encartes=[])["offers"][0]
        for gone in ("store_address", "store_latitude", "store_longitude", "store_geo_source"):
            self.assertNotIn(gone, offer)


class TestBuildPublic(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        db = self.db
        # Seed ran twice: two "Cometa" rows; the lowest id is the retailer.
        db.add_all([Store(name="Cometa", website="https://cometa.example", lat=-3.7, lon=-38.5, address="Rua A"),
                    Store(name="Cometa", website="https://cometa.example"),
                    Store(name="Pão de Açúcar", website="https://pa.example")])
        db.add_all([Product(name="Café Torrado Melitta 500g"), Product(name="Sem preço"),
                    Product(name="Arroz Branco 1kg")])
        db.flush()
        old = datetime.utcnow() - timedelta(days=2)
        db.add_all([
            Price(product_id=1, store_id=1, price=30.00, url="https://x/old", scraped_at=old),
            Price(product_id=1, store_id=1, price=28.99, url="https://x/new", scraped_at=datetime.utcnow()),
            Price(product_id=1, store_id=3, price=31.50, scraped_at=datetime.utcnow()),
            Price(product_id=3, store_id=2, price=0.0, scraped_at=datetime.utcnow()),  # unusable
            Price(product_id=3, store_id=3, price=6.90, scraped_at=datetime.utcnow()),
        ])
        db.commit()

    def tearDown(self):
        self.db.close()

    def build(self, **kw):
        return build_public(self.db, encartes=kw.pop("encartes", []), **kw)

    def test_latest_price_per_retailer_in_cents(self):
        data = self.build()
        cafe = {o["retailer_name"]: o for o in data["offers"] if o["product_id"] == "1"}
        self.assertEqual(cafe["Cometa"]["price_cents"], 2899)   # newest of the two rows
        self.assertEqual(cafe["Cometa"]["source_url"], "https://x/new")
        self.assertEqual(cafe["Pão de Açúcar"]["price_cents"], 3150)

    def test_duplicate_stores_collapse_and_unusable_rows_are_dropped(self):
        data = self.build()
        self.assertEqual(sorted(r["name"] for r in data["retailers"]), ["Cometa", "Pão de Açúcar"])
        self.assertEqual({o["context_id"] for o in data["offers"] if o["retailer_name"] == "Cometa"}, {"1"})
        self.assertEqual([p["name"] for p in data["products"]], ["Arroz Branco 1kg", "Café Torrado Melitta 500g"])
        self.assertEqual(data["coverage"], {"networks": 2, "products": 2, "offers": 3, "exact_pairs": 1})

    def test_product_fields_follow_the_contract(self):
        cafe = next(p for p in self.build()["products"] if p["id"] == "1")
        self.assertEqual((cafe["amount"], cafe["unit"], cafe["pack_count"], cafe["category"]),
                         (500, "g", 1, "Mercearia"))
        offer = self.build()["offers"][0]
        self.assertEqual((offer["channel"], offer["currency"], offer["published"], offer["ttl_hours"]),
                         ("catalog", "BRL", 1, 36))
        self.assertTrue(offer["price_observed_at"].endswith("+00:00"))

    def test_brand_gtin_and_photo_are_exposed_when_the_product_row_has_them(self):
        cafe = self.db.query(Product).filter(Product.id == 1).one()
        cafe.brand, cafe.gtin, cafe.image_url = "Melitta", "7891000100103", "https://img.example/cafe.jpg"
        self.db.commit()
        product = next(p for p in self.build()["products"] if p["id"] == "1")
        self.assertEqual((product["brand"], product["gtin"], product["image_url"]),
                         ("Melitta", "7891000100103", "https://img.example/cafe.jpg"))
        self.assertEqual(product["gtin_evidence"], "Código de barras (EAN) informado pela loja.")

    def test_brand_gtin_and_photo_stay_blank_when_no_member_has_them(self):
        arroz = next(p for p in self.build()["products"] if p["id"] == "3")
        self.assertEqual((arroz["brand"], arroz["gtin"], arroz["gtin_evidence"], arroz["image_url"]),
                         ("", None, None, None))

    def test_brand_gtin_and_photo_are_found_on_any_matched_member_not_just_the_displayed_one(self):
        # The member _display_product picks for its name ("Lasanha Bolonhesa Sadia Pacote 600g", the more
        # detailed one) is not the one that happens to carry the enrichment here - both chains' data about
        # what is, in the end, one product should still surface.
        self.db.add_all([Product(name="LASANHA SADIA BOLONHESA 600G"), Product(name="Lasanha Bolonhesa Sadia Pacote 600g")])
        self.db.flush()
        self.db.query(Product).filter(Product.name == "LASANHA SADIA BOLONHESA 600G").one().gtin = "7891000200104"
        self.db.add_all([Price(product_id=4, store_id=1, price=18.49, scraped_at=datetime.utcnow()),
                         Price(product_id=5, store_id=3, price=21.90, scraped_at=datetime.utcnow())])
        self.db.commit()
        lasanha = next(p for p in self.build()["products"] if "asanha" in p["name"].lower())
        self.assertEqual(lasanha["name"], "Lasanha Bolonhesa Sadia Pacote 600g")  # unaffected: still the best name
        self.assertEqual(lasanha["gtin"], "7891000200104")  # found on the other, less-detailed-named member

    def test_filters(self):
        self.assertEqual([p["name"] for p in self.build(q="CAFE")["products"]], ["Café Torrado Melitta 500g"])
        self.assertEqual(self.build(q="zzz")["products"], [])
        self.assertEqual({o["retailer_name"] for o in self.build(network="3")["offers"]}, {"Pão de Açúcar"})
        self.assertEqual([p["name"] for p in self.build(category="Mercearia")["products"]],
                         ["Arroz Branco 1kg", "Café Torrado Melitta 500g"])
        self.assertEqual(self.build(channel="flyer")["offers"], [])
        self.assertEqual([p["id"] for p in self.build(product="3")["products"]], ["3"])

    def test_same_product_at_two_chains_becomes_one_product_with_two_offers(self):
        self.db.add_all([Product(name="LASANHA SADIA BOLONHESA 600G"), Product(name="Lasanha Bolonhesa Sadia Pacote 600g")])
        self.db.flush()
        self.db.add_all([Price(product_id=4, store_id=1, price=18.49, scraped_at=datetime.utcnow()),
                         Price(product_id=5, store_id=3, price=21.90, scraped_at=datetime.utcnow())])
        self.db.commit()
        data = self.build()
        lasanha = [p for p in data["products"] if "asanha" in p["name"].lower()]
        self.assertEqual(len(lasanha), 1)
        self.assertEqual(lasanha[0]["name"], "Lasanha Bolonhesa Sadia Pacote 600g")
        self.assertEqual(sorted(o["price_cents"] for o in data["offers"] if o["product_id"] == lasanha[0]["id"]),
                         [1849, 2190])
        self.assertEqual(data["coverage"]["exact_pairs"], 2)  # café and lasanha
        # an old shared link to either original id still finds it
        self.assertEqual(len(self.build(product="5")["products"]), 1)
        self.assertEqual(len(self.build(product="4")["products"]), 1)

    def test_deal_details_are_exposed(self):
        self.db.add(Price(product_id=3, store_id=3, price=5.99, regular_price=6.90, offer="13% OFF",
                          scraped_at=datetime.utcnow()))
        self.db.commit()
        arroz = [o for o in self.build()["offers"] if o["product_id"] == "3"]
        self.assertEqual((arroz[0]["price_cents"], arroz[0]["regular_price_cents"], arroz[0]["deal_label"]),
                         (599, 690, "13% OFF"))
        cafe = next(o for o in self.build()["offers"] if o["retailer_name"] == "Cometa")
        self.assertEqual((cafe["regular_price_cents"], cafe["deal_label"]), (None, None))

    def test_stock_is_published_only_when_the_store_reports_it(self):
        self.db.add_all([
            Price(product_id=1, store_id=1, price=20.0, stock=3, scraped_at=datetime.utcnow()),
            Price(product_id=2, store_id=3, price=9.0, scraped_at=datetime.utcnow()),
        ])
        self.db.commit()
        offers = {o["product_id"]: o for o in self.build()["offers"] if o["product_id"] in ("1", "2") and o["retailer_name"] == ("Cometa" if o["product_id"] == "1" else "Pão de Açúcar")}
        self.assertEqual((offers["1"]["stock"], offers["1"]["availability"]), (3, "available"))
        self.assertEqual((offers["2"]["stock"], offers["2"]["availability"]), (None, "unknown"))

    def test_offer_ids_survive_a_new_scrape(self):
        def ids():
            return {(o["product_id"], o["retailer_id"], bool(o["conditions"]["club"])): o["id"]
                    for o in self.build()["offers"]}

        self.db.add(Price(product_id=3, store_id=3, price=5.99, regular_price=7.99, offer="24% OFF · PinClube",
                          scraped_at=datetime.utcnow()))
        self.db.commit()
        before = ids()
        prices_before = {o["id"]: o["price_cents"] for o in self.build()["offers"]}
        for row in self.db.query(Price).all():  # a scrape adds a new price row for every product and store
            self.db.add(Price(product_id=row.product_id, store_id=row.store_id, price=row.price + 1,
                              regular_price=row.regular_price, offer=row.offer, scraped_at=datetime.utcnow()))
        self.db.commit()
        after = ids()
        self.assertTrue(before)
        for key, offer_id in before.items():  # (fresh rows may also revive pairs that had gone stale)
            self.assertEqual(after[key], offer_id)  # the same link still finds the same offer
        self.assertEqual(len(set(after.values())), len(after))  # and ids are unique
        changed = {o["id"]: o["price_cents"] for o in self.build()["offers"]}
        self.assertNotEqual(prices_before, changed)  # while the price itself is the new one

    def test_member_only_price_becomes_a_regular_offer_plus_a_club_offer(self):
        self.db.add(Price(product_id=3, store_id=3, price=5.99, regular_price=7.99, offer="24% OFF · PinClube",
                          scraped_at=datetime.utcnow()))
        self.db.commit()
        arroz = sorted((o for o in self.build()["offers"] if o["product_id"] == "3"), key=lambda o: o["price_cents"])
        club, everyone = arroz
        self.assertEqual((club["price_cents"], club["conditions"]["club"], club["deal_label"]),
                         (599, "PinClube", "24% OFF · PinClube"))
        self.assertEqual((everyone["price_cents"], everyone["conditions"]["club"], everyone["deal_label"]),
                         (799, None, None))
        self.assertNotEqual(club["id"], everyone["id"])

    def test_cometa_flyers(self):
        enc = [Encarte(499, "FEIRÃO COMETA", "Ofertas válidas de 20 a 22/09 em todas as lojas",
                       "https://adminx.example/uploads/a.jpg", None)]
        flyer = self.build(encartes=enc)["flyers"][0]
        self.assertEqual((flyer["title"], flyer["retailer_id"], flyer["retailer_name"]), ("Feirão Cometa", "1", "Cometa"))
        self.assertEqual(flyer["media_pages"], ["https://adminx.example/uploads/a.jpg"])
        self.assertTrue(flyer["valid_from"].endswith("-03:00"))


class TestCategorize(unittest.TestCase):
    def test_the_type_word_decides_not_the_flavour_or_ingredient(self):
        from services.public_api import categorize

        cases = {
            "Macarrão Instantâneo Nissin Lámen Picanha 85g": "Mercearia",
            "LASANHA SADIA FRANGO AO SUGO 600G": "Mercearia",
            "Lasanha Sadia Peito Peru 600g": "Mercearia",
            "Molho de Tomate Heinz 340g": "Mercearia",
            "Espaguete Barilla 500g": "Mercearia",
            "Suco de Laranja Del Valle 1L": "Bebidas",
            "Bebida Láctea Whey Itambé Morango 250ml": "Laticínios e frios",
            "Creme de Leite Nestlé 200g": "Laticínios e frios",
            "Papel Higiênico Neve 12 rolos": "Higiene e beleza",
            "Água Sanitária Qboa 2L": "Limpeza",
            "Ovo Branco Grande 20 un": "Laticínios e frios",
            "Frango Empanado Sadia 500g": "Carnes e peixes",
            "Sadia Peito de Frango 1kg": "Carnes e peixes",
            "BISTECA SUÍNO SADIA CONGELADO FATIADO KG": "Carnes e peixes",
            "Mamão Formosa Granel 2kg": "Hortifruti",
            "Alho Frito Garlic Foods 90g": "Hortifruti",
            "Biscoito Recheado Sabor Chocolate 140g": "Padaria e biscoitos",
            "Cerveja Sabor Limão 350ml": "Bebidas",
            "Cadeira de praia": "Outros",
        }
        for name, expected in cases.items():
            self.assertEqual(categorize(name), expected, name)

    def test_a_flavour_word_alone_does_not_pick_the_category(self):
        from services.public_api import categorize

        self.assertEqual(categorize("Salgadinho Sabor Bacon 100g"), "Mercearia")
        self.assertEqual(categorize("Cadeira Sabor Picanha"), "Outros")


class TestSubcategorize(unittest.TestCase):
    def test_the_specific_cut_wins_over_the_species_it_is_made_of(self):
        from services.public_api import subcategorize

        # Real case: searching "bovina" (the species) used to be the only way these were found, which
        # buried "Maminha" and "Picanha" - specific, searchable cuts - under a shared, generic attribute.
        self.assertEqual(subcategorize("Maminha Bovina Fribal Bandeja Kg"), "Maminha")
        self.assertEqual(subcategorize("Carne Bovina Picanha Bordon Resf Fat Preço por quilo na peça"), "Picanha")
        self.assertEqual(subcategorize("Carne Bovina Moída Patinho Swift Congelada 1kg"), "Patinho")

    def test_a_species_word_alone_with_nothing_more_specific_has_no_subcategory(self):
        from services.public_api import subcategorize

        self.assertEqual(subcategorize("Carne Bovina Korin Moída Congelada Orgânica 400g"), "")
        self.assertEqual(subcategorize("Músculo Bovino Em Pedaço Resfriado Bandeja 700g"), "")

    def test_two_different_kinds_of_product_get_two_different_subcategories(self):
        from services.public_api import subcategorize

        # Real case: both are "Higiene e beleza" at the category level, which used to be the only axis
        # the UI's "similar products" list had to work with.
        self.assertEqual(subcategorize("Hidratante Flor De Ype Ameixa E Flor De Lotus 200ml Frasco"), "Hidratante")
        self.assertEqual(subcategorize("Absorvente Always Noite Seca Com Abas 48 Unidades"), "Absorvente")

    def test_a_name_with_no_specific_keyword_has_no_subcategory(self):
        from services.public_api import subcategorize

        self.assertEqual(subcategorize("Cadeira de praia"), "")


class TestDisplayName(unittest.TestCase):
    def test_all_caps_names_are_title_cased_with_units_in_lower_case(self):
        from services.public_api import display_name

        self.assertEqual(display_name("FILÉ DE PEITO DE FRANGO SADIA BANDEJA 1KG"),
                         "Filé de Peito de Frango Sadia Bandeja 1kg")
        self.assertEqual(display_name("LEITE UHT INTEGRAL PARMALAT 1L"), "Leite UHT Integral Parmalat 1l")
        self.assertEqual(display_name("ABÓBORA JAPONESA/CABOTIÁ KG"), "Abóbora Japonesa/Cabotiá Kg")

    def test_mixed_case_names_keep_their_words_and_get_tidy_units_and_spacing(self):
        from services.public_api import display_name

        self.assertEqual(display_name("Cerveja  Heineken   15X269ML"), "Cerveja Heineken 15x269ml")
        self.assertEqual(display_name("Whisky Escocês Blended 12 Anos"), "Whisky Escocês Blended 12 Anos")
        self.assertEqual(display_name("Azeite Member's Mark 1L"), "Azeite Member's Mark 1l")

    def test_empty_names_do_not_break(self):
        from services.public_api import display_name

        self.assertEqual(display_name(""), "")
        self.assertEqual(display_name("   "), "")


class TestCurrentList(unittest.TestCase):
    """What a store lists changes between scrapes: new items appear, dropped ones disappear, bad runs are ignored."""

    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add_all([Store(name="Pão de Açúcar", website="https://pa.example"),
                         Store(name="Sams Club", website="https://sams.example")])
        self.db.add_all([Product(name="Arroz Branco 1kg"), Product(name="Feijão Carioca 1kg"),
                         Product(name="Café Torrado 500g"), Product(name="Leite Integral 1l")])
        self.db.commit()
        self.clock = datetime.utcnow() - timedelta(hours=10)

    def tearDown(self):
        self.db.close()

    def run_of(self, site_key, store_id, product_ids, run_id, success=True, items=None, price=5.0):
        """One scrape run: its prices tagged with ``run_id`` and its attempt recorded."""
        self.clock += timedelta(hours=1)
        for product_id in product_ids:
            self.db.add(Price(product_id=product_id, store_id=store_id, price=price, run_id=run_id, scraped_at=self.clock))
        self.db.add(ScrapeAttempt(site_key=site_key, success=success, items_found=len(product_ids) if items is None else items,
                                  run_id=run_id, error=None if success else "boom", created_at=self.clock))
        self.db.commit()

    def names(self, store="Pão de Açúcar"):
        data = build_public(self.db, encartes=[])
        by_id = {p["id"]: p["name"] for p in data["products"]}
        return sorted(by_id[o["product_id"]] for o in data["offers"] if o["retailer_name"] == store)

    def error(self, store="Pão de Açúcar"):
        return next(r["last_error"] for r in build_public(self.db, encartes=[])["retailers"] if r["name"] == store)

    def test_new_products_appear_and_dropped_ones_disappear(self):
        self.run_of("pao_de_acucar", 1, [1, 2], "run1")
        self.assertEqual(self.names(), ["Arroz Branco 1kg", "Feijão Carioca 1kg"])
        self.run_of("pao_de_acucar", 1, [2, 3], "run2")  # rice is gone, coffee is new
        self.assertEqual(self.names(), ["Café Torrado 500g", "Feijão Carioca 1kg"])

    def test_the_price_comes_from_the_latest_run(self):
        self.run_of("pao_de_acucar", 1, [1], "run1", price=5.0)
        self.run_of("pao_de_acucar", 1, [1], "run2", price=4.0)
        offer = build_public(self.db, encartes=[])["offers"][0]
        self.assertEqual(offer["price_cents"], 400)

    def test_a_failed_run_does_not_wipe_the_list(self):
        self.run_of("pao_de_acucar", 1, [1, 2], "run1")
        self.run_of("pao_de_acucar", 1, [], "run2", success=False, items=0)
        self.assertEqual(self.names(), ["Arroz Branco 1kg", "Feijão Carioca 1kg"])
        self.assertIn("boom", self.error())

    def test_an_empty_run_does_not_wipe_the_list(self):
        self.run_of("pao_de_acucar", 1, [1, 2], "run1")
        self.run_of("pao_de_acucar", 1, [], "run2", success=True, items=0)
        self.assertEqual(self.names(), ["Arroz Branco 1kg", "Feijão Carioca 1kg"])

    def test_a_run_with_a_quarter_of_the_usual_items_is_accepted(self):
        self.run_of("pao_de_acucar", 1, [1, 2, 3, 4], "run1", items=100)
        self.run_of("pao_de_acucar", 1, [4], "run2", items=25)  # exactly 25% of the usual 100
        self.assertEqual(self.names(), ["Leite Integral 1l"])
        self.assertIsNone(self.error())

    def test_a_run_just_under_a_quarter_is_set_aside(self):
        self.run_of("pao_de_acucar", 1, [1, 2, 3, 4], "run1", items=100)
        self.run_of("pao_de_acucar", 1, [4], "run2", items=24)
        self.assertEqual(self.names(), ["Arroz Branco 1kg", "Café Torrado 500g", "Feijão Carioca 1kg", "Leite Integral 1l"])

    def test_a_partial_run_under_the_threshold_keeps_the_previous_list(self):
        self.run_of("pao_de_acucar", 1, [1, 2, 3, 4] * 5, "run1", items=100)
        self.run_of("pao_de_acucar", 1, [1], "run2", items=10)  # 10 of a usual 100
        self.assertEqual(self.names(), ["Arroz Branco 1kg", "Café Torrado 500g", "Feijão Carioca 1kg", "Leite Integral 1l"])
        self.assertIn("poucos itens", self.error())

    def test_untagged_history_is_kept_until_the_store_has_a_tagged_run(self):
        self.clock += timedelta(hours=1)
        self.db.add(Price(product_id=1, store_id=1, price=5.0, scraped_at=self.clock))  # from before runs were tagged
        self.db.commit()
        self.assertEqual(self.names(), ["Arroz Branco 1kg"])
        self.run_of("pao_de_acucar", 1, [2], "run1")
        self.assertEqual(self.names(), ["Feijão Carioca 1kg"])  # the first tagged run replaces the untagged history

    def test_stores_are_independent(self):
        self.run_of("pao_de_acucar", 1, [1], "pa1")
        self.run_of("sams_club", 2, [2], "sc1")
        self.run_of("pao_de_acucar", 1, [3], "pa2")
        self.assertEqual(self.names("Pão de Açúcar"), ["Café Torrado 500g"])
        self.assertEqual(self.names("Sams Club"), ["Feijão Carioca 1kg"])

    def test_products_no_longer_listed_anywhere_are_not_published(self):
        self.run_of("pao_de_acucar", 1, [1, 2], "run1")
        self.run_of("pao_de_acucar", 1, [2], "run2")
        products = [p["name"] for p in build_public(self.db, encartes=[])["products"]]
        self.assertEqual(products, ["Feijão Carioca 1kg"])


class TestApiPublicRoute(unittest.TestCase):
    def setUp(self):
        from web import app as web_app

        web_app._public_cache.clear()

    def test_route_returns_contract_keys(self):
        from web.app import app

        with patch("web.app.build_public", return_value={"products": []}) as mock_build:
            resp = app.test_client().get("/api/public?q=cafe&network=3&category=Bebidas")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"products": []})
        kwargs = mock_build.call_args.kwargs
        self.assertEqual((kwargs["q"], kwargs["network"], kwargs["category"]), ("cafe", "3", "Bebidas"))

    def test_route_reports_failures_as_json_error(self):
        from web.app import app

        with patch("web.app.build_public", side_effect=RuntimeError("boom")):
            resp = app.test_client().get("/api/public")
        self.assertEqual(resp.status_code, 500)
        self.assertIn("error", resp.get_json())

    def test_repeated_requests_are_served_from_the_cache(self):
        from web.app import app

        with patch("web.app.build_public", return_value={"products": []}) as mock_build:
            client = app.test_client()
            first = client.get("/api/public?q=leite")
            second = client.get("/api/public?q=leite")
            client.get("/api/public?q=cafe")
        self.assertEqual(first.data, second.data)
        self.assertEqual(mock_build.call_count, 2)  # one per distinct filter combination

    def test_cache_expires(self):
        from web import app as web_app

        ttl = web_app.PUBLIC_CACHE_SECONDS
        with patch("web.app.build_public", return_value={"products": []}) as mock_build, \
                patch("web.app.time") as clock:
            clock.monotonic.side_effect = [100.0, 100.0 + ttl - 1, 100.0 + ttl + 1, 100.0 + ttl + 1]
            client = web_app.app.test_client()
            client.get("/api/public")  # built (stored at 100)
            client.get("/api/public")  # still fresh
            client.get("/api/public")  # expired: rebuilt
        self.assertEqual(mock_build.call_count, 2)

    def test_response_carries_cache_headers_and_answers_conditional_requests(self):
        from web.app import app

        with patch("web.app.build_public", return_value={"products": []}):
            client = app.test_client()
            first = client.get("/api/public")
            again = client.get("/api/public", headers={"If-None-Match": first.headers["ETag"]})
        self.assertIn("max-age=60", first.headers["Cache-Control"])
        self.assertEqual(again.status_code, 304)

    def test_failures_are_not_cached(self):
        from web.app import app

        client = app.test_client()
        with patch("web.app.build_public", side_effect=RuntimeError("boom")):
            self.assertEqual(client.get("/api/public").status_code, 500)
        with patch("web.app.build_public", return_value={"products": []}):
            self.assertEqual(client.get("/api/public").status_code, 200)

    def test_cache_is_bounded(self):
        from web import app as web_app

        with patch("web.app.build_public", return_value={"products": []}):
            client = web_app.app.test_client()
            for n in range(web_app.PUBLIC_CACHE_MAX_ENTRIES + 10):
                client.get(f"/api/public?q=busca{n}")
        self.assertEqual(len(web_app._public_cache), web_app.PUBLIC_CACHE_MAX_ENTRIES)


if __name__ == "__main__":
    unittest.main()
