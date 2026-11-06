"""The barcode a receipt prints on each item line: read, validated, and kept through the tile merge."""

import json
import unittest

from receiptocr.consensus import consensus_merge
from receiptocr.parser import clean_code, code_read, parse_reply_json
from receiptocr.schemas import Item

COCA_COLA = "7894900011517"  # real EAN-13 (Coca-Cola 2 L): its check digit holds


class TestCleanCode(unittest.TestCase):
    def test_a_valid_barcode_is_kept_whatever_the_spacing(self):
        self.assertEqual(clean_code(f" {COCA_COLA} "), COCA_COLA)
        self.assertEqual(clean_code("7894900-011517"), COCA_COLA)

    def test_one_misread_digit_gives_no_code_rather_than_another_product(self):
        self.assertIsNone(clean_code("7894900011518"))

    def test_internal_plu_numbers_and_blanks_are_not_barcodes(self):
        for value in ("", None, "1234", "000123", "0000000000000"):
            self.assertIsNone(clean_code(value))


class TestParseAndMerge(unittest.TestCase):
    def reply(self, code):
        return json.dumps({"items": [{
            "line": "001", "code": code, "name": "REFRIG COCA COLA 2L", "qty": 1, "unit": "un",
            "unit_price": 9.99, "discount": None, "printed_total": 9.99,
        }]})

    def test_the_code_comes_through_the_parser(self):
        self.assertEqual(parse_reply_json(self.reply(COCA_COLA))[0].code, COCA_COLA)

    def test_a_reply_without_a_code_field_still_parses(self):
        self.assertIsNone(parse_reply_json(self.reply("")).pop().code)
        raw = json.dumps({"items": [{"line": "1", "name": "ARROZ", "qty": 1, "unit_price": 5.0, "printed_total": 5.0}]})
        self.assertIsNone(parse_reply_json(raw)[0].code)

    def test_overlapping_tiles_keep_the_code_the_reading_that_has_one_found(self):
        seen = Item(line_no=1, name="REFRIG COCA COLA 2L", code=COCA_COLA, qty=1, unit_price=9.99, total=9.99, printed_total=9.99)
        cut = Item(line_no=1, name="REFRIG COCA COLA 2L", code=None, qty=1, unit_price=9.99, total=9.99, printed_total=9.99)
        merged, _ = consensus_merge([[seen], [cut]])
        self.assertEqual(merged[0].code, COCA_COLA)


class TestCodeReads(unittest.TestCase):
    """What the model transcribed, kept even when its check digit fails, so a caller can repair a one-digit slip."""

    def test_a_code_the_check_digit_rejects_still_comes_through_as_a_read(self):
        slipped = "7894900011518"  # one digit off COCA_COLA
        self.assertEqual(code_read(slipped), [slipped])
        self.assertEqual(code_read(" 0789-4900011517 "), ["07894900011517"])

    def test_what_cannot_be_a_barcode_is_no_read(self):
        for value in ("", None, "1234", "0000000000000", "12345678901234567", "abc"):
            self.assertEqual(code_read(value), [])

    def test_the_parser_keeps_the_read_and_still_gives_no_validated_code(self):
        reply = json.dumps({"items": [{"line": "1", "code": "7894900011518", "name": "COCA COLA", "qty": 1,
                                       "unit": "un", "unit_price": 9.99, "printed_total": 9.99}]})
        item = parse_reply_json(reply)[0]
        self.assertIsNone(item.code)
        self.assertEqual(item.code_reads, ["7894900011518"])

    def test_the_merge_lists_each_distinct_read_most_voted_first(self):
        def item(code, reads):
            return Item(line_no=1, name="REFRIG COCA COLA 2L", code=code, code_reads=reads, qty=1,
                        unit_price=9.99, total=9.99, printed_total=9.99)

        slip = "789490001151"  # a dropped digit
        merged, _ = consensus_merge([[item(None, [slip])], [item(None, [slip])], [item(COCA_COLA, [COCA_COLA])]])
        self.assertEqual(merged[0].code_reads, [slip, COCA_COLA])  # two readings agree on the slip, one on the rest
        self.assertEqual(merged[0].code, COCA_COLA)

    def test_the_merge_keeps_no_more_than_a_handful(self):
        reads = [f"78949000115{n:02d}" for n in range(10)]
        items = [[Item(line_no=1, name="X Y", code_reads=[r], qty=1, unit_price=1, total=1, printed_total=1)] for r in reads]
        self.assertLessEqual(len(consensus_merge(items)[0][0].code_reads), 6)


# Trying the extractor on real receipt photos. They show the buyer's CPF, so they are kept out of the repo (the
# folder is in .gitignore): put .jpg/.png photos in tests/fixtures/receipts-private/, set OLLAMA_API_KEY, and
# uncomment this to see which lines come back with a barcode. It calls the provider, so it is not a unit test.
#
# import os
# from pathlib import Path
# from receiptocr import ReceiptExtractor
#
# PHOTOS = Path(__file__).parent / "fixtures" / "receipts-private"
#
#
# @unittest.skipUnless(os.getenv("OLLAMA_API_KEY") and PHOTOS.is_dir(), "needs a key and photos in receipts-private/")
# class TestRealReceipts(unittest.TestCase):
#     def test_most_lines_come_back_with_a_barcode(self):
#         for photo in sorted(PHOTOS.glob("*.[jp][pn]g")):
#             items = ReceiptExtractor().extract(str(photo)).items
#             coded = [i for i in items if i.code]
#             print(f"{photo.name}: {len(coded)} of {len(items)} lines with a barcode")
#             self.assertGreater(len(coded), len(items) // 2)


if __name__ == "__main__":
    unittest.main()
