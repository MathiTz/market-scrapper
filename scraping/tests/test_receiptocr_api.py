"""Tests for POST /api/receipt/ocr (scraping/receiptocr/ via local_api.app).

The extractor is always mocked: no test ever calls the ollama.com API.
"""

import io
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

# Must be set before local_api.app imports config: never touch the real market.db.
os.environ["DATABASE_URL"] = "sqlite://"

# local_api.app must import with or without the optional OCR extras (that is part of what is tested), so
# this import is unconditional; the error types below only exist once requirements-ocr.txt is installed.
from local_api import app as app_module  # noqa: E402
from local_api.app import app  # noqa: E402

OCR_INSTALLED = app_module.ReceiptExtractor is not None
if OCR_INSTALLED:
    from receiptocr.schemas import (  # noqa: E402
        AuthenticationError,
        BadReplyError,
        BadRequestError,
        ModelNotFoundError,
        ProviderUnavailableError,
        QuotaError,
        RateLimitedError,
        ReceiptOcrError,
    )


@dataclass
class FakeItem:
    line_no: int = 1
    name: str = "ARROZ BRANCO 5KG"
    qty: float = 1.0
    unit: str = "UN"
    unit_price: float = 24.9
    discount: float = 2.0
    total: float = 22.9
    printed_total: float = 22.9
    contested: bool = False


@dataclass
class FakeFlags:
    bad_math: list = field(default_factory=list)
    missing_lines: list = field(default_factory=list)
    duplicate_lines: list = field(default_factory=list)


@dataclass
class FakeTimings:
    slice_ms: float = 1.0
    ocr_ms: float = 2.0
    merge_ms: float = 3.0
    total_ms: float = 6.0


@dataclass
class FakeReceipt:
    items: list = field(default_factory=lambda: [FakeItem()])
    flags: FakeFlags = field(default_factory=FakeFlags)
    timings: FakeTimings = field(default_factory=FakeTimings)
    raw: list = field(default_factory=list)
    failed_tiles: list = field(default_factory=list)

    @property
    def degraded(self):
        return bool(self.failed_tiles)


# A valid 10x10 PNG: the route accepts decodable images.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x02\x00\x00\x00\x02PX\xea"
    b"\x00\x00\x00\x1fIDAT\x18\x19}\xc1\x01\x01\x00\x00\x00@ \xfe\x9f\xf6@\xc9\x92%K\x96,Y\xb2d\xc9"
    b"\x92\x15\x07\xdf\x00\x0b)\xdf\x97\xe9\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestReceiptOcrNotInstalled(unittest.TestCase):
    """Runs everywhere: without requirements-ocr.txt the route says so instead of failing."""

    def test_ocr_not_installed_returns_503(self):
        with patch("local_api.app.ReceiptExtractor", None):
            resp = app.test_client().post("/api/receipt/ocr", data={})
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.get_json())


@unittest.skipUnless(OCR_INSTALLED, "optional OCR dependencies (requirements-ocr.txt) are not installed")
class TestReceiptOcrRoute(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        key = patch.dict(os.environ, {"OLLAMA_API_KEY": "test-key"})  # the route refuses to run without one
        key.start()
        self.addCleanup(key.stop)

    def _post(self, data=None, **kwargs):
        if data is None:
            data = {"image": (io.BytesIO(PNG_BYTES), "receipt.png", "image/png")}
        return self.client.post("/api/receipt/ocr", data=data, **kwargs)

    def test_missing_file_returns_400(self):
        resp = self._post(data={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_empty_file_returns_400(self):
        resp = self._post(data={"image": (io.BytesIO(b""), "receipt.png", "image/png")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_non_image_file_returns_400(self):
        resp = self._post(data={"image": (io.BytesIO(b"This is a text file, not an image."), "receipt.txt", "text/plain")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_non_image_content_with_image_extension_returns_400(self):
        resp = self._post(data={"image": (io.BytesIO(b"corrupt-data-not-an-image"), "receipt.png", "image/png")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_oversized_file_returns_413(self):
        # Limit is 10 MB
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        resp = self._post(data={"image": (io.BytesIO(oversized), "huge.png", "image/png")})
        self.assertEqual(resp.status_code, 413)
        self.assertIn("error", resp.get_json())

    def test_success_returns_receipt_json(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.return_value = FakeReceipt()
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["items"][0]["name"], "ARROZ BRANCO 5KG")
        self.assertEqual(data["items"][0]["total"], 22.9)
        self.assertIn("flags", data)
        self.assertIn("timings", data)
        self.assertIn("raw", data)
        self.assertEqual(data["failed_tiles"], [])
        self.assertFalse(data["degraded"])

    def test_degraded_receipt_exposes_flag(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.return_value = FakeReceipt(failed_tiles=[2])
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["degraded"])

    def test_authentication_error_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = AuthenticationError("bad key")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())
        # The provider detail (and with it any credential hint) must not leak.
        self.assertNotIn("bad key", resp.get_data(as_text=True))

    def test_quota_error_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = QuotaError("out of credits")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_model_not_found_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = ModelNotFoundError("model missing")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_bad_reply_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = BadReplyError("garbage body")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_provider_error_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = ProviderUnavailableError("timeout")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_rate_limit_returns_429_with_retry_after(self):
        error = RateLimitedError("provider rate limit")
        # Set like the library does (receiptocr sets the attribute in _classify).
        error.retry_after = 7
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.headers.get("Retry-After"), "7")
        self.assertIn("error", resp.get_json())

    def test_rate_limit_returns_429_without_retry_after(self):
        error = RateLimitedError("provider rate limit")
        error.retry_after = None
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 429)
        self.assertNotIn("Retry-After", resp.headers)
        self.assertIn("error", resp.get_json())

    def test_missing_api_key_is_a_503_and_the_extractor_is_never_reached(self):
        # The key is this server's configuration, not the caller's photo: it must not read as "check the
        # image" (the old 400), and nothing should be uploaded to the provider without one.
        env_without = {k: v for k, v in os.environ.items() if k != "OLLAMA_API_KEY"}
        with patch.dict(os.environ, env_without, clear=True):
            with patch("local_api.app.ReceiptExtractor") as mock_extractor:
                resp = self._post()
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.get_json())
        mock_extractor.assert_not_called()

    def test_an_empty_api_key_counts_as_missing(self):
        with patch.dict(os.environ, {"OLLAMA_API_KEY": ""}):
            with patch("local_api.app.ReceiptExtractor") as mock_extractor:
                resp = self._post()
        self.assertEqual(resp.status_code, 503)
        mock_extractor.assert_not_called()

    def test_bad_request_maps_to_400(self):
        error = BadRequestError("provider rejected request (HTTP 400)")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_plain_receipt_error_with_other_message_maps_to_502(self):
        # A plain ReceiptOcrError is never matched by its text: the upload was already decoded
        # successfully by the route, so whatever the library raises beyond the typed errors is the
        # provider's side - a 502.
        error = ReceiptOcrError("All tiles failed extraction after retry attempts.")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def _extract_and_capture_path(self, outcome):
        """POST with an extractor that records the file it was handed; ``outcome`` is its result or error."""
        seen = {}

        def extract(path):
            seen["path"] = path
            seen["existed_during"] = os.path.exists(path)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = extract
            resp = self._post()
        return resp, seen

    def test_temp_file_exists_during_extraction_and_is_removed_after_it_fails(self):
        resp, seen = self._extract_and_capture_path(AuthenticationError("bad key"))
        self.assertEqual(resp.status_code, 502)
        self.assertTrue(seen["existed_during"])
        self.assertFalse(os.path.exists(seen["path"]))

    def test_temp_file_is_removed_after_success(self):
        resp, seen = self._extract_and_capture_path(FakeReceipt())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(seen["existed_during"])
        self.assertFalse(os.path.exists(seen["path"]))

    def test_temp_file_is_removed_after_an_unexpected_error(self):
        resp, seen = self._extract_and_capture_path(RuntimeError("boom"))
        self.assertEqual(resp.status_code, 502)
        self.assertFalse(os.path.exists(seen["path"]))

    def test_a_decompression_bomb_is_refused_from_its_header_before_it_is_decoded(self):
        # Real case: a 144-megapixel PNG is ~17 KB on the wire and used to make the route's own validity
        # check allocate ~860 MB. The size is now read from the header and refused first.
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("1", (12000, 12000)).save(buffer, "PNG")
        self.assertLess(buffer.tell(), 100 * 1024)  # tiny on the wire: the byte cap alone cannot catch it
        with patch("cv2.imdecode") as decode, patch("local_api.app.ReceiptExtractor") as mock_extractor:
            resp = self._post(data={"image": (io.BytesIO(buffer.getvalue()), "bomb.png", "image/png")})
        self.assertEqual(resp.status_code, 413)
        decode.assert_not_called()
        mock_extractor.assert_not_called()

    def test_a_format_the_extractor_cannot_read_is_refused(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, "GIF")
        resp = self._post(data={"image": (io.BytesIO(buffer.getvalue()), "receipt.gif", "image/gif")})
        self.assertEqual(resp.status_code, 400)

    def test_a_truncated_image_with_a_valid_header_is_refused_before_the_extractor(self):
        # A good header with the pixel data cut off passes the header check but not the decode: it is the
        # caller's file, so it is a 400 here rather than an "unreadable image" error from the library.
        from PIL import Image

        buffer = io.BytesIO()
        Image.effect_noise((200, 200), 80).convert("RGB").save(buffer, "PNG")
        truncated = buffer.getvalue()[: len(buffer.getvalue()) // 3]
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            resp = self._post(data={"image": (io.BytesIO(truncated), "receipt.png", "image/png")})
        self.assertEqual(resp.status_code, 400)
        mock_extractor.assert_not_called()

    def test_an_oversized_body_is_refused_while_it_is_received_not_after_it_is_buffered(self):
        # Well past the file limit plus the multipart envelope: Flask's MAX_CONTENT_LENGTH answers (as JSON,
        # through the 413 handler) without the route ever reading the file into memory.
        too_big = b"x" * (11 * 1024 * 1024)
        resp = self._post(data={"image": (io.BytesIO(too_big), "huge.png", "image/png")})
        self.assertEqual(resp.status_code, 413)
        self.assertIn("error", resp.get_json())

    def test_unexpected_error_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = RuntimeError("boom")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()