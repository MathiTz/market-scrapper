import os
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
