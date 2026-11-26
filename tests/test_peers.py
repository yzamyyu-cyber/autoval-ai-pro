import unittest
from autoval.peers import peer_groups, screen_peers, TICKER_INDUSTRY


class PeerGroupTests(unittest.TestCase):
    def test_msft_software(self):
        self.assertIn("core_software", peer_groups("MSFT"))

    def test_googl_internet_platforms(self):
        g = peer_groups("GOOGL")
        self.assertTrue(g, "GOOGL should have a configured peer group")
        self.assertIn("core", g)
        self.assertIn("META", g["core"])

    def test_tsla_electric_vehicles(self):
        g = peer_groups("TSLA")
        self.assertTrue(g, "TSLA should have a configured peer group")
        self.assertIn("legacy_automakers", g)
        self.assertIn("F", g["legacy_automakers"])
        self.assertIn("GM", g["legacy_automakers"])

    def test_aapl_consumer_technology(self):
        self.assertIn("core", peer_groups("AAPL"))

    def test_hd_retail(self):
        g = peer_groups("HD")
        self.assertIn("core", g)
        self.assertIn("LOW", g["core"])

    def test_unknown_ticker_no_peers(self):
        self.assertEqual(peer_groups("ZZZZ"), {})

    def test_amzn_ecommerce_cloud(self):
        g = peer_groups("AMZN")
        self.assertTrue(g, "AMZN should have configured peer groups")
        self.assertIn("retail", g)
        self.assertIn("ecommerce", g)
        self.assertIn("cloud_platform", g)
        self.assertIn("advertising", g)
        self.assertIn("WMT", g["retail"])
        self.assertIn("MSFT", g["cloud_platform"])
        self.assertIn("META", g["advertising"])
        # no duplicate share class (GOOGL only, never GOOG alongside)
        self.assertNotIn("GOOG", g["cloud_platform"] + g["advertising"])


class ScreenPeersTests(unittest.TestCase):
    def _ok(self):
        return {"market_cap": 100, "ttm_eps": 5, "ttm_ebitda": 50, "ev": 200, "valued": True}

    def test_rejects_missing_field(self):
        p = self._ok(); p.pop("ttm_ebitda")
        r = screen_peers({"A": p})
        self.assertEqual(r["valid"], {})
        self.assertTrue(any("ttm_ebitda" in e["reason"] for e in r["excluded"]))

    def test_rejects_not_valued(self):
        p = self._ok(); p["valued"] = False
        r = screen_peers({"A": p})
        self.assertEqual(r["valid"], {})

    def test_accepts_valid(self):
        r = screen_peers({"A": self._ok()})
        self.assertIn("A", r["valid"])


if __name__ == "__main__":
    unittest.main()
