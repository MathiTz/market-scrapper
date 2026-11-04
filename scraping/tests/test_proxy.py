import os
import sys
import types
import unittest
from unittest import mock

import requests

from scraper.base import proxy_for
from scraper.sites.atacadao import AtacadaoScraper
from scraper.sites.pinheiro import PinheiroScraper


class ChainProxyTests(unittest.TestCase):
    def test_only_the_chain_with_a_proxy_uses_it(self):
        with mock.patch.dict(os.environ, {"PROXY_ATACADAO": "socks5h://127.0.0.1:1080"}):
            behind = AtacadaoScraper()
            direct = PinheiroScraper()
        self.assertEqual(behind.session.proxies["https"], "socks5h://127.0.0.1:1080")
        self.assertEqual(behind.proxy_kwargs, {"proxy": "socks5://127.0.0.1:1080"})  # the browser resolves names itself
        self.assertEqual(direct.session.proxies, {})
        self.assertEqual(direct.proxy_kwargs, {})

    def test_an_empty_setting_means_no_proxy(self):
        with mock.patch.dict(os.environ, {"PROXY_PAO_DE_ACUCAR": ""}):
            self.assertIsNone(proxy_for("pao_de_acucar"))


class ChromeFallbackTests(unittest.TestCase):
    """A 403 to the plain client is tried again with a Chrome-like handshake (curl_cffi), through the same proxy."""

    def refused(self):
        return requests.HTTPError("403", response=mock.MagicMock(status_code=403))

    def fake_curl_cffi(self, status=200, text="ok"):
        module = types.ModuleType("curl_cffi")
        module.requests = mock.MagicMock()
        module.requests.get.return_value = mock.MagicMock(status_code=status, text=text)
        return module

    def test_a_403_is_retried_like_chrome_through_the_chains_proxy(self):
        fake = self.fake_curl_cffi()
        with mock.patch.dict(os.environ, {"PROXY_ATACADAO": "socks5h://127.0.0.1:1080"}):
            scraper = AtacadaoScraper()
        with mock.patch.object(AtacadaoScraper, "_fetch_with_retry", side_effect=self.refused()), \
                mock.patch.dict(sys.modules, {"curl_cffi": fake, "curl_cffi.requests": fake.requests}):
            self.assertEqual(scraper.fetch_raw("https://x.test/api"), "ok")
        kwargs = fake.requests.get.call_args.kwargs
        self.assertEqual((kwargs["impersonate"], kwargs["proxies"]["https"]), ("chrome", "socks5h://127.0.0.1:1080"))

    def test_other_errors_are_not_retried_that_way(self):
        fake = self.fake_curl_cffi()
        not_found = requests.HTTPError("404", response=mock.MagicMock(status_code=404))
        with mock.patch.object(PinheiroScraper, "_fetch_with_retry", side_effect=not_found), \
                mock.patch.dict(sys.modules, {"curl_cffi": fake, "curl_cffi.requests": fake.requests}):
            with self.assertRaises(requests.HTTPError):
                PinheiroScraper().fetch_raw("https://x.test/api")
        fake.requests.get.assert_not_called()

    def test_still_refused_like_chrome_keeps_the_status_for_the_caller(self):
        fake = self.fake_curl_cffi(status=429, text="error code: 1015")
        with mock.patch.object(PinheiroScraper, "_fetch_with_retry", side_effect=self.refused()), \
                mock.patch.dict(sys.modules, {"curl_cffi": fake, "curl_cffi.requests": fake.requests}):
            with self.assertRaises(requests.HTTPError) as caught:
                PinheiroScraper().fetch_raw("https://x.test/api")
        self.assertEqual(caught.exception.response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
