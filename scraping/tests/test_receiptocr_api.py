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

from local_api.app import app  # noqa: E402
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


class TestReceiptOcrRoute(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

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

    def test_missing_api_key_maps_to_400(self):
        error = ReceiptOcrError("Missing Ollama API key. Provide api_key or set OLLAMA_API_KEY environment variable.")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_missing_api_key_via_env_maps_to_400(self):
        # The extractor is patched: without the patch this would fire a real request
        # whenever a scraping/.env with OLLAMA_API_KEY exists (the library reads it
        # from the CWD), so the env manipulation alone must never reach the network.
        error = ReceiptOcrError("Missing Ollama API key. Provide api_key or set OLLAMA_API_KEY environment variable.")
        env_without = {k: v for k, v in os.environ.items() if k != "OLLAMA_API_KEY"}
        with patch.dict(os.environ, env_without, clear=True):
            with patch("local_api.app.ReceiptExtractor") as mock_extractor:
                mock_extractor.return_value.extract.side_effect = error
                resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


    def test_bad_request_maps_to_400(self):
        error = BadRequestError("provider rejected request (HTTP 400)")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_unreadable_image_error_maps_to_400(self):
        error = ReceiptOcrError("Unreadable image: /tmp/fake.jpg")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_plain_receipt_error_with_other_message_maps_to_502(self):
        # Only the two known caller-fault messages map to 400 (pinned to
        # receiptocr's wording); anything else the library raises is a 502.
        error = ReceiptOcrError("All tiles failed extraction after retry attempts.")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_temp_file_is_removed_after_extraction_fails(self):
        import glob
        before = set(glob.glob("/tmp/tmp*.jpg")) | set(glob.glob("/tmp/tmp*.png"))
        error = AuthenticationError("bad key")
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = error
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        after = set(glob.glob("/tmp/tmp*.jpg")) | set(glob.glob("/tmp/tmp*.png"))
        self.assertEqual(before, after)

    def test_temp_file_is_removed_after_success(self):
        import glob
        before = set(glob.glob("/tmp/tmp*.jpg")) | set(glob.glob("/tmp/tmp*.png"))
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.return_value = FakeReceipt()
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        after = set(glob.glob("/tmp/tmp*.jpg")) | set(glob.glob("/tmp/tmp*.png"))
        self.assertEqual(before, after)

    def test_unexpected_error_maps_to_502(self):
        with patch("local_api.app.ReceiptExtractor") as mock_extractor:
            mock_extractor.return_value.extract.side_effect = RuntimeError("boom")
            resp = self._post()
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_ocr_not_installed_returns_503(self):
        with patch("local_api.app.ReceiptExtractor", None):
            resp = self._post()
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()