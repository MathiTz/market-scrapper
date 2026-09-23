"""Tests for site scraper behavior, parsed from real captured pages."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from scraper.flyer_ocr import FlyerOffer
from scraper.sites.cometa import CometaScraper
from scraper.sites.atacadao import AtacadaoScraper
from scraper.sites.mercadinho import MercadinhoScraper
from scraper.sites.pao_de_acucar import PaoDeAcucarScraper
from scraper.sites.pinheiro import PinheiroScraper
from scraper.sites.sams_club import SamsClubScraper

FIXTURES = Path(__file__).parent / "fixtures"


class TestPaoDeAcucarScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = PaoDeAcucarScraper()
        html = (FIXTURES / "pao_de_acucar_home.html").read_text(encoding="utf-8")
        self.soup = BeautifulSoup(html, "lxml")
        self.by_name = {p.product_name: p for p in self.scraper.parse_offers(self.soup)}

    def test_one_product_per_id_despite_carousel_clones(self):
        # The fixture holds 6 products plus a slick-cloned duplicate of the first.
        self.assertEqual(len(self.by_name), 6)

    def test_name_excludes_price_text(self):
        self.assertIn("Margarina Cremosa com Sal Qualy Pote 500g", self.by_name)

    def test_percent_off_uses_deal_price(self):
        p = self.by_name["Margarina Cremosa com Sal Qualy Pote 500g"]
        self.assertEqual((p.price, p.regular_price, p.offer), (7.49, 9.99, "25% OFF"))
        self.assertEqual(p.store_name, "Pão de Açúcar")
        self.assertEqual(
            p.url,
            "https://www.paodeacucar.com/produto/71812/margarina-cremosa-com-sal-qualy-pote-500g",
        )

    def test_per_kg_price(self):
        p = self.by_name["Peito De Frango Com Osso Resfriado 1,2kg"]
        self.assertEqual((p.price, p.regular_price), (17.52, 21.90))

    def test_multi_buy_keeps_regular_price(self):
        # "A unid. sai por" only applies when buying 2+; a single unit costs full price.
        for name, offer, price in [
            ("Carne Moída De Patinho Resfriada QUALITÁ 500G", "10% na 2ª unidade", 38.90),
            ("Queijo Parmesão Ralado Vigor Pacote 100g Embalagem Econômica", "Leve 3 e pague 2", 13.50),
        ]:
            p = self.by_name[name]
            self.assertEqual((p.price, p.offer, p.regular_price), (price, offer, None))

    def test_item_without_deal(self):
        p = self.by_name["Batata Pré-Frita Carinhas Congelada Bem Brasil Pacote 400g"]
        self.assertEqual((p.price, p.offer, p.regular_price), (17.99, None, None))

    def test_limit(self):
        self.assertEqual(len(self.scraper.parse_offers(self.soup, limit=2)), 2)

    @patch.object(PaoDeAcucarScraper, "render")
    def test_scrape_renders_home_with_scroll(self, mock_render):
        mock_render.return_value = self.soup
        results = self.scraper.scrape()
        self.assertEqual(len(results), 6)
        args, kwargs = mock_render.call_args
        self.assertEqual(args[0], "https://www.paodeacucar.com")
        self.assertTrue(kwargs["scroll"])

    @patch.object(PaoDeAcucarScraper, "render")
    def test_scrape_raises_on_bot_check(self, mock_render):
        mock_render.return_value = BeautifulSoup(
            "<html><head><title>Verificação de segurança</title></head></html>", "lxml"
        )
        with self.assertRaises(RuntimeError):
            self.scraper.scrape()

    def test_clean_price_brazilian_format(self):
        self.assertEqual(self.scraper._clean_price("R$ 1.234,56"), 1234.56)


class TestPaoDeAcucarBranches(unittest.TestCase):
    """Real branches from GPA's own nationwide store-locator file (see scraper/sites/pao_de_acucar.py)."""

    def setUp(self):
        self.scraper = PaoDeAcucarScraper()
        self.payload = (FIXTURES / "pao_de_acucar_lojas.json").read_text(encoding="utf-8")

    @patch.object(PaoDeAcucarScraper, "fetch_raw")
    def test_only_this_chains_own_banner_in_ceara_is_kept(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branches = self.scraper.fetch_locations()
        # 7 entries: "Minuto PA" and "Posto Pão de Açúcar" are different banners; "Ibirapuera" is the
        # right banner but in São Paulo; one name ("Náutico") repeated.
        self.assertEqual({b.name for b in branches}, {"Náutico", "Júlio Ventura", "Coco"})
        self.assertNotIn("Ibirapuera", {b.name for b in branches})

    @patch.object(PaoDeAcucarScraper, "fetch_raw")
    def test_address_joins_street_neighbourhood_and_city_cleanly(self, mock_fetch):
        mock_fetch.return_value = self.payload
        nautico = next(b for b in self.scraper.fetch_locations() if b.name == "Náutico")
        self.assertEqual(nautico.address, "Av da Abolição, 2900, Meireles, Fortaleza")  # no padding left in

    @patch.object(PaoDeAcucarScraper, "fetch_raw")
    def test_a_neighbourhood_of_just_a_dash_is_left_out_not_kept_as_text(self, mock_fetch):
        mock_fetch.return_value = self.payload
        coco = next(b for b in self.scraper.fetch_locations() if b.name == "Coco")
        self.assertNotIn(" - ", coco.address)
        self.assertEqual(coco.address, "Av. Eng. Santana Jr., 2277, Shopping Casa Blanca Mall, Fortaleza")

    @patch.object(PaoDeAcucarScraper, "fetch_raw")
    def test_has_no_coordinates_yet(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.assertTrue(all(b.lat is None and b.lon is None for b in self.scraper.fetch_locations()))

    @patch.object(PaoDeAcucarScraper, "fetch_raw")
    def test_needs_no_browser_a_plain_request_answers_it(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.scraper.fetch_locations()
        self.assertEqual(mock_fetch.call_args.args[0], "https://static.gpa.digital/json/locator/store-locator-pa.json")

    @patch.object(PaoDeAcucarScraper, "fetch_raw", side_effect=RuntimeError("timed out"))
    def test_a_failed_fetch_returns_nothing_rather_than_raise(self, _):
        self.assertEqual(self.scraper.fetch_locations(), [])


class TestCometaScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = CometaScraper()
        self.payload = (FIXTURES / "cometa_encartes.json").read_text(encoding="utf-8")

    def test_media_url_resolves_to_cms_host(self):
        self.assertEqual(
            self.scraper.media_url("/uploads/a.jpg"),
            "https://adminx.cometasupermercados.com.br/uploads/a.jpg",
        )
        self.assertEqual(self.scraper.media_url("https://cdn.example/a.jpg"), "https://cdn.example/a.jpg")

    @patch.object(CometaScraper, "fetch_raw")
    def test_fetch_encartes_resolves_image_and_pdf_urls(self, mock_fetch):
        mock_fetch.return_value = self.payload
        encartes = self.scraper.fetch_encartes()
        mock_fetch.assert_called_once_with("https://cometasupermercados.com.br/api/encartes")
        self.assertEqual(len(encartes), 2)
        first = encartes[0]
        self.assertEqual(first.name, "FEIRÃO COMETA")
        self.assertIn("20 a 22/09", first.description)
        self.assertTrue(first.cover_url.startswith("https://adminx.cometasupermercados.com.br/uploads/"))
        self.assertTrue(first.cover_url.endswith(".jpg"))
        self.assertTrue(first.pdf_url.endswith(".pdf"))

    @patch.object(CometaScraper, "fetch_raw")
    def test_encarte_without_cover_is_skipped(self, mock_fetch):
        data = json.loads(self.payload)
        data["data"][0]["cover"] = None
        mock_fetch.return_value = json.dumps(data)
        self.assertEqual(len(self.scraper.fetch_encartes()), 1)

    @patch("scraper.sites.cometa.flyer_ocr.ocr_available", return_value=False)
    @patch.object(CometaScraper, "fetch_raw")
    def test_scrape_without_easyocr_returns_no_products(self, mock_fetch, _):
        mock_fetch.return_value = self.payload
        self.assertEqual(self.scraper.scrape(), [])

    @patch("scraper.sites.cometa.flyer_ocr.read_offers")
    @patch("scraper.sites.cometa.flyer_ocr.ocr_available", return_value=True)
    @patch.object(CometaScraper, "_fetch_with_retry")
    @patch.object(CometaScraper, "fetch_raw")
    def test_scrape_reads_flyers_and_keeps_lowest_price_per_product(self, mock_fetch, mock_get, _, mock_read):
        mock_fetch.return_value = self.payload
        mock_get.return_value.content = b"image"
        mock_read.side_effect = [
            [FlyerOffer("Açúcar cristal OLHO D'ÁGUA 1kg", 2.79, 3.39, 17)],
            [FlyerOffer("açúcar cristal olho d'água 1kg", 2.59, 3.39, 24),
             FlyerOffer("Aveia NESTLÉ 170g", 3.49, 5.15, 32)],
        ]
        results = self.scraper.scrape()
        self.assertEqual(mock_get.call_count, 2)
        by_name = {p.product_name.casefold(): p for p in results}
        self.assertEqual(len(results), 2)
        sugar = by_name["açúcar cristal olho d'água 1kg"]
        self.assertEqual((sugar.price, sugar.regular_price, sugar.offer), (2.59, 3.39, "24% de desconto"))
        self.assertEqual(sugar.store_name, "Cometa")
        self.assertTrue(sugar.url.startswith("https://adminx.cometasupermercados.com.br/uploads/"))

    @patch("scraper.sites.cometa.flyer_ocr.read_offers")
    @patch("scraper.sites.cometa.flyer_ocr.ocr_available", return_value=True)
    @patch.object(CometaScraper, "_fetch_with_retry")
    @patch.object(CometaScraper, "fetch_raw")
    def test_scrape_skips_a_flyer_that_fails(self, mock_fetch, mock_get, _, mock_read):
        mock_fetch.return_value = self.payload
        mock_get.return_value.content = b"image"
        mock_read.side_effect = [RuntimeError("model download failed"),
                                 [FlyerOffer("Aveia NESTLÉ 170g", 3.49, 5.15, 32)]]
        self.assertEqual([p.product_name for p in self.scraper.scrape()], ["Aveia NESTLÉ 170g"])


class TestCometaBranches(unittest.TestCase):
    """Real branches from Cometa's own "Onde Estamos" API (see scraper/sites/cometa.py)."""

    def setUp(self):
        self.scraper = CometaScraper()
        self.payload = (FIXTURES / "cometa_onde_estamos.json").read_text(encoding="utf-8")

    @patch.object(CometaScraper, "fetch_raw")
    def test_parses_each_valid_branch_once(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branches = self.scraper.fetch_locations()
        # 6 entries: one repeated id, one with unparsable coordinates, one with no address
        self.assertEqual({b.external_id for b in branches}, {"116", "137", "84"})

    @patch.object(CometaScraper, "fetch_raw")
    def test_the_loja_prefix_is_dropped_from_the_name(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branch = next(b for b in self.scraper.fetch_locations() if b.external_id == "116")
        self.assertEqual(branch.name, "Ildefonso Albano")
        self.assertEqual(branch.address, "Rua Ildefonso Albano, 2260 – Aldeota")

    @patch.object(CometaScraper, "fetch_raw")
    def test_coordinates_come_straight_from_the_source_no_geocoding_needed(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branch = next(b for b in self.scraper.fetch_locations() if b.external_id == "116")
        self.assertAlmostEqual(branch.lat, -3.740611194601686)
        self.assertAlmostEqual(branch.lon, -38.51615591974627)

    @patch.object(CometaScraper, "fetch_raw")
    def test_needs_no_extra_headers_a_plain_request_is_enough(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.scraper.fetch_locations()
        self.assertEqual(mock_fetch.call_args.args[0], "https://cometasupermercados.com.br/api/onde-estamos")

    @patch.object(CometaScraper, "fetch_raw")
    def test_follows_pagination_across_pages(self, mock_fetch):
        page1 = {"data": [json.loads(self.payload)["data"][0]],
                 "meta": {"pagination": {"page": 1, "pageSize": 1, "pageCount": 2, "total": 2}}}
        page2 = {"data": [json.loads(self.payload)["data"][1]],
                 "meta": {"pagination": {"page": 2, "pageSize": 1, "pageCount": 2, "total": 2}}}
        mock_fetch.side_effect = [json.dumps(page1), json.dumps(page2)]
        branches = self.scraper.fetch_locations()
        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual({b.external_id for b in branches}, {"116", "137"})

    @patch.object(CometaScraper, "fetch_raw", side_effect=RuntimeError("timed out"))
    def test_a_failed_fetch_returns_nothing_rather_than_raise(self, _):
        self.assertEqual(self.scraper.fetch_locations(), [])


class TestPinheiroScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = PinheiroScraper()
        html = (FIXTURES / "pinheiro_ofertas.html").read_text(encoding="utf-8")
        self.soup = BeautifulSoup(html, "lxml")
        self.by_name = {p.product_name: p for p in self.scraper.parse_offers(self.soup)}

    def test_parses_each_product_once(self):
        self.assertEqual(len(self.by_name), 4)  # the fixture repeats its first card

    def test_daily_offer(self):
        p = self.by_name["Refrigerante H2oh Limao 500ml Pet"]
        self.assertEqual((p.price, p.regular_price, p.offer), (4.29, 4.59, "7% OFF"))
        self.assertTrue(p.url.startswith("https://www.lojaonline.pinheirosupermercado.com.br/produto/"))

    def test_club_price_is_labelled(self):
        p = self.by_name["Biscoito Erika Especial Cebolinha 300g"]
        self.assertEqual((p.price, p.regular_price, p.offer), (7.59, 9.99, "24% OFF · PinClube"))

    def test_name_is_the_full_name_not_the_brand_link(self):
        self.assertIn("Lava Roupas Liquido Ariel Cores Radiantes 700ml Refil", self.by_name)
        self.assertNotIn("Ariel", self.by_name)

    def test_product_without_a_deal(self):
        p = self.by_name["Cha Tres Coracoes Camomila 25g Capsula"]
        self.assertEqual((p.price, p.regular_price, p.offer), (24.99, None, None))

    @patch.object(PinheiroScraper, "render")
    def test_scrape_renders_the_offers_page(self, mock_render):
        mock_render.return_value = self.soup
        self.assertEqual(len(self.scraper.scrape()), 4)  # no API answer: the rendered cards are used
        self.assertEqual(mock_render.call_args.args[0], "https://www.lojaonline.pinheirosupermercado.com.br/ofertas")


class _Page:
    """Stands in for the browser page a page action receives."""

    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error

    def wait_for_selector(self, selector, timeout=None):
        return None

    def wait_for_timeout(self, ms):
        return None

    def evaluate(self, js):
        if self.error:
            raise self.error
        return self.answer


class TestPinheiroOffersApi(unittest.TestCase):
    def setUp(self):
        self.scraper = PinheiroScraper()
        self.items = json.loads((FIXTURES / "pinheiro_offers.json").read_text(encoding="utf-8"))
        self.by_name = {p.product_name: p for p in self.scraper.parse_api_offers(self.items)}

    def test_reads_each_available_product_once(self):
        # 7 items: one repeated, one sold out
        self.assertEqual(len(self.by_name), 5)
        self.assertNotIn("Peito De Peru Seara Fatiado 150g", self.by_name)

    def test_daily_offer(self):
        p = self.by_name["Refrigerante H2oh Limao 500ml Pet"]
        self.assertEqual((p.price, p.regular_price, p.offer), (4.29, 4.59, "7% OFF"))
        self.assertEqual(p.url, "https://www.lojaonline.pinheirosupermercado.com.br/produto/14/refrigerante-h2oh-limao-500ml-pet")

    def test_matches_what_the_card_shows(self):
        # The rendered-card fixture shows the same product with the same price, old price and label.
        card = {p.product_name: p for p in self.scraper.parse_offers(BeautifulSoup(
            (FIXTURES / "pinheiro_ofertas.html").read_text(encoding="utf-8"), "lxml"))}
        for name in ("Refrigerante H2oh Limao 500ml Pet", "Biscoito Erika Especial Cebolinha 300g"):
            api, shown = self.by_name[name], card[name]
            self.assertEqual((api.price, api.regular_price, api.offer, api.url), (shown.price, shown.regular_price, shown.offer, shown.url))

    def test_club_price_is_labelled(self):
        p = self.by_name["Biscoito Erika Especial Cebolinha 300g"]
        self.assertEqual((p.price, p.regular_price, p.offer), (7.59, 9.99, "24% OFF · PinClube"))

    def test_price_for_several_units_does_not_replace_the_shelf_price(self):
        p = self.by_name["Cha Tres Coracoes Camomila 25g Capsula"]
        self.assertEqual((p.price, p.regular_price), (24.99, 27.49))  # what one unit costs
        self.assertEqual(p.offer, "9% OFF · 2 un por R$ 18,74 cada")

    def test_a_centavo_of_difference_is_not_a_discount(self):
        item = json.loads(json.dumps(self.items[2]))  # the tiered one
        item["produto_id"] = 998
        item["oferta"].update(preco_oferta="28.39", preco_antigo="28.40")
        p = self.scraper.parse_api_offers([item])[0]
        self.assertEqual((p.price, p.regular_price, p.offer), (28.39, None, "2 un por R$ 18,74 cada"))

    def test_leve_e_pague_has_no_price_cut_only_the_condition(self):
        p = self.by_name["Suco Kapo Laranja 200ml Tp"]
        self.assertEqual((p.price, p.regular_price, p.offer), (2.19, None, "Leve 6 pague 5"))

    def test_weighed_product_keeps_its_price(self):
        self.assertEqual(self.by_name["Laranja Pera 1kg (aprox. 5 Und.)"].price, 1.99)

    def test_the_orders_limit_is_not_recorded_as_stock(self):
        self.assertTrue(all(p.stock is None for p in self.by_name.values()))

    def test_items_without_a_usable_price_are_skipped(self):
        broken = json.loads(json.dumps(self.items[0]))
        broken["produto_id"] = 999
        broken["oferta"]["preco_oferta"] = "0"
        self.assertEqual(self.scraper.parse_api_offers([broken]), [])

    def test_limit(self):
        self.assertEqual(len(self.scraper.parse_api_offers(self.items, limit=2)), 2)

    @patch.object(PinheiroScraper, "render")
    def test_scrape_uses_the_api_when_it_answers(self, mock_render):
        page = _Page({"error": None, "items": self.items})

        def render(url, wait_seconds=0, page_action=None):
            page_action(page)
            return BeautifulSoup("<html></html>", "lxml")  # no cards: they are not needed

        mock_render.side_effect = render
        self.assertEqual(len(self.scraper.scrape()), 5)

    @patch.object(PinheiroScraper, "render")
    def test_scrape_keeps_what_was_read_when_the_api_stops_early(self, mock_render):
        page = _Page({"error": "status 500 on page 3", "items": self.items[:2]})

        def render(url, wait_seconds=0, page_action=None):
            page_action(page)
            return BeautifulSoup("<html></html>", "lxml")

        mock_render.side_effect = render
        self.assertEqual(len(self.scraper.scrape()), 2)

    @patch.object(PinheiroScraper, "render")
    def test_scrape_falls_back_to_the_cards_when_reading_the_api_fails(self, mock_render):
        page = _Page(error=RuntimeError("page closed"))
        cards = BeautifulSoup((FIXTURES / "pinheiro_ofertas.html").read_text(encoding="utf-8"), "lxml")

        def render(url, wait_seconds=0, page_action=None):
            page_action(page)  # must not raise: Scrapling would only log it
            return cards

        mock_render.side_effect = render
        self.assertEqual(len(self.scraper.scrape()), 4)


class TestPinheiroBranches(unittest.TestCase):
    """Real branches from Pinheiro's own "Nossas Lojas" institutional page (see scraper/sites/pinheiro.py)."""

    def setUp(self):
        self.scraper = PinheiroScraper()
        self.html = (FIXTURES / "pinheiro_nossas_lojas.html").read_text(encoding="utf-8")

    def test_parses_each_real_branch(self):
        branches = self.scraper._parse_locations_html(self.html)
        self.assertEqual({b.name for b in branches},
                         {"Acaraú", "Aquiraz", "Porto das Dunas", "Praia de Iracema"})

    def test_keeps_the_real_address_html_entities_undone(self):
        aquiraz = next(b for b in self.scraper._parse_locations_html(self.html) if b.name == "Aquiraz")
        self.assertEqual(aquiraz.address, "Av. Nossa Sra. de Lurdes, 77 - Centro")
        self.assertEqual(aquiraz.external_id, "Aquiraz")

    def test_a_multi_line_entry_with_a_phone_number_still_parses(self):
        iracema = next(b for b in self.scraper._parse_locations_html(self.html) if b.name == "Praia de Iracema")
        self.assertEqual(iracema.address, "Av. Monsenhor Tabosa, 697 - Praia de Iracema")

    def test_has_no_coordinates_yet(self):
        self.assertTrue(all(b.lat is None and b.lon is None for b in self.scraper._parse_locations_html(self.html)))

    def test_the_distribution_centre_is_not_a_branch(self):
        names = {b.name for b in self.scraper._parse_locations_html(self.html)}
        self.assertFalse(any("Distribui" in n or "CD" in n for n in names))

    def test_malformed_or_empty_html_yields_nothing(self):
        self.assertEqual(self.scraper._parse_locations_html(""), [])
        self.assertEqual(self.scraper._parse_locations_html("<html><body>no stores here</body></html>"), [])

    def test_fetch_locations_reads_the_page_and_parses_it(self):
        page = _Page({"error": None, "html": self.html})

        def render(url, wait_seconds=0, page_action=None):
            page_action(page)
            return None

        with patch.object(PinheiroScraper, "render", side_effect=render), patch.object(PinheiroScraper, "close"):
            branches = self.scraper.fetch_locations()
        self.assertEqual(len(branches), 4)

    def test_fetch_locations_returns_nothing_rather_than_raise_when_the_page_action_fails(self):
        page = _Page(error=RuntimeError("no request seen"))

        def render(url, wait_seconds=0, page_action=None):
            page_action(page)  # must not raise: Scrapling would only log it
            return None

        with patch.object(PinheiroScraper, "render", side_effect=render), patch.object(PinheiroScraper, "close"):
            self.assertEqual(self.scraper.fetch_locations(), [])


class TestSamsClubScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = SamsClubScraper()
        self.products = json.loads((FIXTURES / "sams_products.json").read_text(encoding="utf-8"))

    def test_discounted_product_becomes_an_offer(self):
        price, list_price, quantity = self.scraper._commercial_offer(self.products["discounted"][0])
        offer = self.scraper._to_product_price(self.products["discounted"][0], price, list_price, quantity)
        self.assertEqual((offer.price, offer.regular_price, offer.offer), (39.89, 58.98, "32% OFF"))
        self.assertGreater(quantity, 0)
        self.assertTrue(offer.url.startswith("https://www.samsclub.com.br/"))

    def test_brand_gtin_and_photo_are_read_when_the_source_gives_them(self):
        product = self.products["discounted"][0]
        price, list_price, quantity = self.scraper._commercial_offer(product)
        offer = self.scraper._to_product_price(product, price, list_price, quantity)
        self.assertEqual(offer.brand, "Dove")
        self.assertEqual(offer.gtin, "7891150102583")
        self.assertEqual(offer.image_url, "https://samsclub.vtexassets.com/arquivos/ids/123456/dove.jpg")

    def test_brand_gtin_and_photo_are_none_when_the_source_gives_none(self):
        # Real case: most products in this same category listing carry no brand/ean/images at all.
        product = self.products["discounted"][1]
        price, list_price, quantity = self.scraper._commercial_offer(product)
        offer = self.scraper._to_product_price(product, price, list_price, quantity)
        self.assertEqual((offer.brand, offer.gtin, offer.image_url), (None, None, None))

    def test_a_placeholder_ean_is_not_kept(self):
        from scraper.vtex import _ean

        for bad in ["0", "00000000", None, "", "123", "12345678901234567"]:
            self.assertIsNone(_ean(bad), bad)
        self.assertEqual(_ean("7891150102583"), "7891150102583")

    def test_a_real_stock_number_is_kept_and_a_placeholder_is_not(self):
        product = json.loads(json.dumps(self.products["discounted"][0]))
        price, list_price, _ = self.scraper._commercial_offer(product)
        self.assertEqual(self.scraper._to_product_price(product, price, list_price, 7).stock, 7)
        self.assertIsNone(self.scraper._to_product_price(product, price, list_price, 10000).stock)  # "not tracked"
        self.assertIsNone(self.scraper._to_product_price(product, price, list_price, 99999).stock)

    @patch.object(SamsClubScraper, "fetch_raw")
    def test_category_stops_at_the_first_product_without_a_discount(self, mock_fetch):
        page = {"products": self.products["discounted"] + self.products["not_discounted"]}
        mock_fetch.return_value = json.dumps(page)
        offers = self.scraper._category_offers("bebidas", cap=100)
        self.assertEqual(len(offers), 3)
        self.assertEqual(mock_fetch.call_count, 1)  # sorted by discount: no need to read page 2
        params = mock_fetch.call_args.kwargs["params"]
        self.assertEqual((params["page"], params["sort"]), (1, "discount:desc"))
        self.assertIn("/category-1/bebidas", mock_fetch.call_args.args[0])

    @patch.object(SamsClubScraper, "fetch_raw")
    def test_unavailable_products_are_skipped(self, mock_fetch):
        sold_out = json.loads(json.dumps(self.products["discounted"][0]))
        sold_out["items"][0]["sellers"][0]["commertialOffer"]["AvailableQuantity"] = 0
        mock_fetch.return_value = json.dumps({"products": [sold_out] + self.products["discounted"][1:]})
        self.assertEqual(len(self.scraper._category_offers("bebidas", cap=100)), 2)

    @patch.object(SamsClubScraper, "fetch_raw")
    def test_scrape_spans_categories_without_duplicates(self, mock_fetch):
        mock_fetch.return_value = json.dumps({"products": self.products["discounted"] + self.products["not_discounted"]})
        results = self.scraper.scrape()
        self.assertEqual(len(results), 3)  # the same products come back for every category
        self.assertEqual(mock_fetch.call_count, len(self.scraper.categories))

    @patch.object(SamsClubScraper, "fetch_raw", side_effect=RuntimeError("blocked"))
    def test_scrape_raises_when_every_category_fails(self, _):
        with self.assertRaises(RuntimeError):
            self.scraper.scrape()


class TestAtacadaoScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = AtacadaoScraper()
        self.payload = (FIXTURES / "atacadao_products.json").read_text(encoding="utf-8")

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_price_list_keeps_products_without_a_discount(self, mock_fetch):
        mock_fetch.return_value = self.payload
        offers = self.scraper._category_offers("mercearia", cap=100)
        self.assertEqual(len(offers), 3)
        self.assertTrue(all(o.regular_price is None and o.offer is None for o in offers))
        self.assertTrue(all(o.price > 0 and o.store_name == "Atacadão" for o in offers))
        self.assertTrue(offers[0].url.startswith("https://www.atacadao.com.br/"))

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_does_not_ask_for_discount_sorting(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.scraper._category_offers("bebidas", cap=100)
        self.assertNotIn("sort", mock_fetch.call_args.kwargs["params"])
        self.assertIn("/category-1/bebidas", mock_fetch.call_args.args[0])

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_cap_limits_each_category(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.assertEqual(len(self.scraper._category_offers("mercearia", cap=2)), 2)

    def test_registered_with_the_other_scrapers(self):
        from scraper.sites import SCRAPER_MAP
        self.assertIs(SCRAPER_MAP["atacadao"], AtacadaoScraper)


class TestVtexBranches(unittest.TestCase):
    """Real branches from VTEX's pickup-points API (see scraper/vtex.py), with their real coordinates."""

    def setUp(self):
        self.scraper = AtacadaoScraper()
        self.payload = (FIXTURES / "vtex_pickup_points.json").read_text(encoding="utf-8")

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_parses_each_active_branch_once(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branches = self.scraper.fetch_locations()
        # 5 entries: one inactive, one with no coordinates, one repeated id
        self.assertEqual({b.external_id for b in branches},
                         {"atacadaobr619_autoservico_fortaleza_fatima", "atacadaobr177_atacado_curitiba"})

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_coordinates_come_straight_from_the_source_lon_lat_order(self, mock_fetch):
        mock_fetch.return_value = self.payload
        branch = next(b for b in self.scraper.fetch_locations() if b.external_id == "atacadaobr619_autoservico_fortaleza_fatima")
        self.assertEqual((branch.lat, branch.lon), (-3.758612, -38.534733))
        self.assertEqual(branch.name, "Atacadão - FORTALEZA FATIMA")
        self.assertIn("Fortaleza", branch.address)

    @patch.object(AtacadaoScraper, "fetch_raw")
    def test_queries_around_fortaleza(self, mock_fetch):
        mock_fetch.return_value = self.payload
        self.scraper.fetch_locations()
        params = mock_fetch.call_args.kwargs["params"]
        self.assertEqual(params["geoCoordinates"], "-38.5267;-3.7319")
        self.assertEqual(params["countryCode"], "BRA")

    @patch.object(AtacadaoScraper, "fetch_raw", side_effect=RuntimeError("timed out"))
    def test_a_failed_fetch_returns_nothing_rather_than_raise(self, _):
        self.assertEqual(self.scraper.fetch_locations(), [])

    def test_sams_club_shares_the_same_branch_parsing(self):
        from scraper.sites.sams_club import SamsClubScraper
        self.assertTrue(hasattr(SamsClubScraper(), "fetch_locations"))


class TestMercadinhoScraper(unittest.TestCase):
    @patch.object(MercadinhoScraper, "_scrape_json", return_value=[])
    @patch.object(MercadinhoScraper, "_scroll_to_bottom")
    @patch.object(MercadinhoScraper, "_click_show_all")
    @patch.object(MercadinhoScraper, "_dismiss_modal")
    @patch.object(MercadinhoScraper, "_wait_for_products")
    @patch.object(MercadinhoScraper, "_create_driver")
    def test_scrape_returns_an_empty_list_not_none_when_nothing_is_found(self, mock_driver, *_):
        mock_driver.return_value.page_source = "<html><body></body></html>"
        self.assertEqual(MercadinhoScraper().scrape(), [])

    def test_scrape_prefers_the_json_and_falls_back_to_the_cards_without_it(self):
        scraper = MercadinhoScraper()
        from scraper.base import ProductPrice

        card = ProductPrice("Mercadinho São Luiz", "Da tela", 1.0, "u")
        with patch.object(MercadinhoScraper, "_scrape_json", return_value=[card]), \
                patch.object(MercadinhoScraper, "_scrape_cards") as cards:
            self.assertEqual(scraper.scrape(), [card])
            cards.assert_not_called()
        with patch.object(MercadinhoScraper, "_scrape_json", return_value=[]), \
                patch.object(MercadinhoScraper, "_scrape_cards", return_value=[card]) as cards:
            self.assertEqual(scraper.scrape(), [card])
            cards.assert_called_once()


class TestMercadappBranches(unittest.TestCase):
    """Real branches (see scraper/mercadapp.py), shared by Mercadinho and Carnaúba."""

    def setUp(self):
        self.body = (FIXTURES / "mercadapp_branches.json").read_text(encoding="utf-8")

    def test_parses_each_real_branch_once(self):
        branches = MercadinhoScraper._parse_locations([self.body])
        self.assertEqual(len(branches), 3)  # 5 entries: one repeated id, one blank name
        self.assertEqual({b.external_id for b in branches}, {"355", "369", "383"})

    def test_keeps_the_chains_own_id_name_and_address(self):
        oliveira = next(b for b in MercadinhoScraper._parse_locations([self.body]) if b.external_id == "355")
        self.assertEqual(oliveira.name, "Oliveira Paiva")
        self.assertEqual(oliveira.address, "OLIVEIRA PAIVA, 170, C DOS FUNCIONARIOS, Fortaleza, CE")

    def test_has_no_coordinates_yet(self):
        # This source gives only a text address; services.store_locations geocodes it before storing.
        self.assertTrue(all(b.lat is None and b.lon is None for b in MercadinhoScraper._parse_locations([self.body])))

    def test_malformed_or_empty_responses_are_ignored(self):
        self.assertEqual(MercadinhoScraper._parse_locations(["not json", "[]", "null", self.body]), MercadinhoScraper._parse_locations([self.body]))

    def test_fetch_locations_opens_the_delivery_dialog_and_reads_the_capture(self):
        driver = unittest.mock.MagicMock()
        driver.execute_script.side_effect = lambda script: (1 if "length" in script else [self.body])
        with patch.object(MercadinhoScraper, "_create_driver", return_value=driver), \
                patch.object(MercadinhoScraper, "_open_delivery_method_dialog") as dialog:
            branches = MercadinhoScraper().fetch_locations()
        dialog.assert_called_once_with(driver)
        self.assertEqual(len(branches), 3)
        driver.quit.assert_called_once()

    def test_fetch_locations_returns_nothing_rather_than_raise_when_the_driver_fails(self):
        with patch.object(MercadinhoScraper, "_create_driver", side_effect=RuntimeError("no chromedriver")):
            self.assertEqual(MercadinhoScraper().fetch_locations(), [])

    def test_carnauba_shares_the_same_branch_parsing(self):
        from scraper.sites.carnauba import CarnaubaScraper

        self.assertEqual(len(CarnaubaScraper._parse_locations([self.body])), 3)
        self.assertEqual(CarnaubaScraper.brand_id, "27")
        self.assertEqual(MercadinhoScraper.brand_id, "221")


class TestMercadinhoOffers(unittest.TestCase):
    NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.scraper = MercadinhoScraper()
        self.body = (FIXTURES / "mercadinho_offers.json").read_text(encoding="utf-8")
        self.items = json.loads(self.body)["mixes"][0]["items"]

    def item(self, **changes):
        base = json.loads(json.dumps(self.items[0]))
        base.update(changes)
        return base

    def parse(self, *items, **kw):
        body = json.dumps({"mixes": [{"id": 1, "items": list(items)}]})
        return self.scraper.parse_offers([body], now=self.NOW, **kw)

    def test_reads_the_products_from_the_captured_responses(self):
        products = self.scraper.parse_offers([self.body], now=self.NOW)
        self.assertEqual(len(products), 4)
        red_bull = products[0]
        self.assertEqual((red_bull.product_name, red_bull.price, red_bull.regular_price, red_bull.offer),
                         ("ENERGÉTICO RED BULL 250ML", 9.99, 11.57, "14% OFF"))
        self.assertEqual(red_bull.stock, self.items[0]["stock"])
        self.assertEqual(red_bull.store_name, "Mercadinho São Luiz")
        self.assertTrue(red_bull.url.startswith("https://mercadinhossaoluiz.com.br/"))

    def test_the_same_product_in_several_sections_counts_once(self):
        self.assertEqual(len(self.scraper.parse_offers([self.body, self.body], now=self.NOW)), 4)

    def test_sold_out_products_are_left_out(self):
        self.assertEqual(self.parse(self.item(stock=0)), [])
        self.assertEqual(len(self.parse(self.item(stock=None))), 1)  # unknown stock is kept

    def test_the_stock_is_kept_when_reported_and_unknown_otherwise(self):
        self.assertEqual(self.parse(self.item(stock=8))[0].stock, 8)
        self.assertIsNone(self.parse(self.item(stock=None))[0].stock)

    def test_offers_that_ended_or_have_not_started_are_left_out(self):
        offer = self.items[0]["offers"][0]
        ended = [{**offer, "end_at": "2026-09-20T20:00:00.000-03:00"}]
        future = [{**offer, "start_at": "2026-09-25T00:00:00.000-03:00"}]
        running = [{**offer, "start_at": "2026-09-20T00:00:00.000-03:00", "end_at": "2026-09-30T20:00:00.000-03:00"}]
        self.assertEqual(self.parse(self.item(offers=ended)), [])
        self.assertEqual(self.parse(self.item(offers=future)), [])
        self.assertEqual(len(self.parse(self.item(offers=running))), 1)
        self.assertEqual(len(self.parse(self.item(offers=[{**ended[0], "unlimited_end": True}]))), 1)

    def test_a_product_without_a_discount_has_no_regular_price_or_label(self):
        product = self.parse(self.item(price=5.0, original_price=5.0))[0]
        self.assertEqual((product.price, product.regular_price, product.offer), (5.0, None, None))

    def test_the_sites_own_offer_title_is_used_as_the_label(self):
        self.assertEqual(self.parse(self.item(offer_title="Leve 3 pague 2"))[0].offer, "Leve 3 pague 2")

    def test_unusable_items_are_skipped(self):
        bad = [self.item(price=0), self.item(price=None), self.item(description="", short_description=""), self.item(id=None)]
        self.assertEqual(self.parse(*bad), [])

    def test_malformed_responses_are_ignored(self):
        products = self.scraper.parse_offers(["not json", "[]", '{"mixes": null}', "null", self.body], now=self.NOW)
        self.assertEqual(len(products), 4)

    def test_limit_caps_the_result(self):
        self.assertEqual(len(self.scraper.parse_offers([self.body], limit=2, now=self.NOW)), 2)


if __name__ == "__main__":
    unittest.main()
