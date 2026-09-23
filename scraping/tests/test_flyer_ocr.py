"""Tests for flyer OCR validation, run on real EasyOCR output (no easyocr needed)."""

import dataclasses
import json
import unittest
from pathlib import Path

from scraper.flyer_ocr import FlyerOffer, TextBox, extract_offers, fix_units, parse_price

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    data = json.loads((FIXTURES / f"flyer_ocr_{name}.json").read_text(encoding="utf-8"))
    return [TextBox(**b) for b in data["boxes"]], data["width"], data["height"]


class TestParsePrice(unittest.TestCase):
    def test_formats(self):
        for text, expected in [("4,99", 4.99), ("6.49", 6.49), ("499", 4.99), ("1599", 15.99),
                               ("'999", 9.99), ("(2299)", 22.99)]:
            self.assertEqual(parse_price(text), expected, text)

    def test_not_prices(self):
        for text in ["350g", "15g", "Por:", "23%", "5,2", "89", "", "1kg"]:
            self.assertIsNone(parse_price(text), text)


class TestFixUnits(unittest.TestCase):
    def test_repairs_misread_sizes(self):
        for text, expected in [
            ("Açucar cristal OLHO D'ÁGUA Jko", "Açucar cristal OLHO D'ÁGUA 1kg"),
            ("Arroz TIO JOÃO lkg", "Arroz TIO JOÃO 1kg"),
            ("Feijão CAMIL 1ko", "Feijão CAMIL 1kg"),
            ("Farinha I kq", "Farinha 1kg"),
            ("sem glúten 20Og", "sem glúten 200g"),
        ]:
            self.assertEqual(fix_units(text), expected, text)

    def test_leaves_real_sizes_and_words_alone(self):
        for text in ["Açúcar demerara ÁSTER 1kg", "Arroz 5kg", "Café 0,1kg", "Sabão 21kg", "Ikea kit", "Bijko", "Jkoy 500g",
                     "Leite em pó NINHO 350g"]:
            self.assertEqual(fix_units(text), text, text)


class TestExtractOffers(unittest.TestCase):
    def offers(self, name, boxes=None):
        loaded, width, height = load(name)
        return extract_offers(boxes or loaded, width, height)

    def test_alimento_flyer(self):
        self.assertEqual(
            self.offers("alimento"),
            [
                FlyerOffer("Leite em pó NINHO adulto semidesnatado lata 350g", 15.99, 22.99, 30),
                FlyerOffer("Açúcar demerara ÁSTER 1kg", 4.99, 6.49, 23),
                FlyerOffer("Aveia NESTLÉ 170g (flocos ou flocos finos)", 3.49, 5.15, 32),
                FlyerOffer("Granola CEREAL CROCK sem glúten 200g (zero açúcar)", 14.99, 18.79, 20),
            ],
        )

    def test_flyer_whose_badge_disagrees_with_its_prices_is_dropped(self):
        # "3 CORAÇÕES" is printed 32% off but 9,49 -> 6,99 is 26%: unverifiable, so skipped.
        names = [o.name for o in self.offers("alimento")]
        self.assertFalse(any("CORAÇÕES" in n for n in names))

    def test_montese_flyer_prices_match_the_printed_flyer(self):
        prices = {(o.price, o.regular_price, o.discount_pct) for o in self.offers("montese")}
        self.assertEqual(
            prices,
            {(2.79, 3.39, 17), (2.49, 3.29, 24), (10.49, 17.99, 41), (23.99, 37.69, 36), (17.99, 23.99, 25)},
        )

    def test_a_misread_one_kilo_size_is_repaired(self):
        # The flyer's "1kg" is read as "Jko" (confidence 0.47), which would stay a word in the name
        # and keep the product from matching the same sugar at another chain.
        names = [o.name for o in self.offers("montese")]
        self.assertIn("Açucar cristal OLHO D'ÁGUA 1kg", names)
        self.assertFalse(any("Jko" in n for n in names))

    def test_names_have_no_stray_price_fragments(self):
        for o in self.offers("montese"):
            self.assertRegex(o.name.split()[0], r"^[^\W\d_]", o.name)

    def test_misread_price_is_rejected(self):
        # 9 read as 2 (4,99 -> 4,29) breaks the 23% check, so the offer must vanish.
        boxes, _, _ = load("alimento")
        corrupted = [dataclasses.replace(b, text="429") if (b.text, int(b.x0)) == ("499", 930) else b for b in boxes]
        self.assertEqual(sum(b.text == "429" for b in corrupted), 1)
        names = [o.name for o in self.offers("alimento", corrupted)]
        self.assertFalse(any("demerara" in n for n in names))
        self.assertEqual(len(names), 3)

    def test_prices_read_with_low_confidence_are_ignored(self):
        boxes, _, _ = load("alimento")
        weak = [dataclasses.replace(b, conf=0.2) if b.text == "499" else b for b in boxes]
        self.assertEqual(len(self.offers("alimento", weak)), 3)

    def test_no_badges_no_offers(self):
        boxes, _, _ = load("alimento")
        no_badges = [b for b in boxes if not b.text.endswith("%")]
        self.assertEqual(self.offers("alimento", no_badges), [])


if __name__ == "__main__":
    unittest.main()
