"""Prices read from a flyer PDF's text layer: a name paired with its price by position and size."""

import unittest

from scraper import flyer_pdf as fp
from tests.pdf_helpers import make_pdf, product


def read(texts, **kwargs):
    return [(o.price, o.name) for o in fp.read_offers(make_pdf(texts, **kwargs))]


class TestReadOffers(unittest.TestCase):
    def test_a_name_above_its_price_is_paired_with_it_one_product_per_cell(self):
        texts = (product(60, 300, ["Arroz Camil", "Branco Tipo 1", "1Kg"], "4", "99")
                 + product(260, 300, ["Café Santa Clara", "Tradicional ou Premium", "250g"], "12", "49"))
        self.assertEqual(sorted(read(texts)), [
            (4.99, "Arroz Camil Branco Tipo 1 1Kg"), (12.49, "Café Santa Clara Tradicional ou Premium 250g"),
        ])

    def test_a_price_per_kilo_says_so_in_the_name(self):
        texts = product(60, 300, ["Linguiça Calabresa Seara", "Tradicional"], "20", "90", unit="quilo")
        self.assertEqual(read(texts), [(20.9, "Linguiça Calabresa Seara Tradicional (kg)")])

    def test_prices_on_a_page_twice_the_width_read_the_same(self):
        # an A3 flyer: everything doubled, as the generator scales it
        doubled = [(x * 2, top * 2, size * 2, text) for x, top, size, text in product(60, 300, ["Arroz Camil"], "4", "99")]
        self.assertEqual(read(doubled, width=1190, height=1684), [(4.99, "Arroz Camil")])

    def test_a_member_price_under_com_o_cpf_no_caixa_is_not_the_shelf_price(self):
        regular = product(60, 300, ["Refresco em Pó Maratá", "25g"], "0", "89")
        # the yellow box under it: "COM O CPF NO CAIXA", then the lower price
        member = [(60, 388, 8, "COM"), (80, 388, 8, "O"), (90, 388, 8, "CPF"), (108, 388, 8, "NO"), (122, 388, 8, "CAIXA")]
        member += [(60, 410, 10, "R$"), (74, 400, 36, "0"), (90, 402, 16, "69"), (74, 440, 5, "cada")]
        self.assertEqual(read(regular + member), [(0.89, "Refresco em Pó Maratá 25g")])

    def test_a_section_title_and_a_headline_are_not_taken_for_a_name(self):
        texts = product(60, 300, ["Vela Vida Luz"], "4", "39")
        texts += [(60, 270, 7, "Bazar"), (200, 40, 50, "NEGÓCIO"), (200, 120, 20, "02 a 05")]
        self.assertEqual(read(texts), [(4.39, "Vela Vida Luz")])

    def test_a_price_with_no_name_near_it_is_left_out_rather_than_guessed(self):
        texts = product(60, 300, ["Arroz Camil"], "4", "99")
        lonely = [(400, 600, 7, "R$"), (409, 593, 33, "9"), (423, 595, 15, "90"), (412, 617, 5, "cada")]
        self.assertEqual(read(texts + lonely), [(4.99, "Arroz Camil")])

    def test_two_cells_side_by_side_each_keep_their_own_name(self):
        texts = product(60, 300, ["Detergente Uze Clean", "Vários Tipos"], "4", "99")
        texts += product(190, 300, ["Detergente Juá", "Neutro"], "7", "99")
        got = dict((name, price) for price, name in read(texts))
        self.assertEqual(got, {"Detergente Uze Clean Vários Tipos": 4.99, "Detergente Juá Neutro": 7.99})

    def test_a_flat_image_page_with_no_text_gives_nothing(self):
        self.assertEqual(read([]), [])

    def test_a_broken_file_is_an_error_not_a_silent_empty_list(self):
        with self.assertRaises(Exception):
            fp.read_offers(b"not a pdf")


if __name__ == "__main__":
    unittest.main()
