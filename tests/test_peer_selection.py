"""Automatic peer-selection regression tests (deterministic + mocked network)."""
import unittest
from unittest.mock import patch

from autoval.peers import (
    discover_peers, is_financial_sic, get_company_sic, peer_groups, screen_peers,
    DUPLICATE_SHARE_CLASSES,
)


class DiscoveryTests(unittest.TestCase):
    def test_curated_groups_for_mapped_ticker(self):
        r = discover_peers("MSFT")
        self.assertEqual(r["method"], "curated")
        self.assertIn("core_software", r["groups"])
        self.assertNotIn("MSFT", r["groups"]["core_software"]["tickers"])  # target excluded

    def test_amazon_groups_remain_economically_distinct(self):
        r = discover_peers("AMZN")
        keys = set(r["groups"].keys())
        self.assertIn("retail", keys)
        self.assertIn("cloud_platform", keys)
        self.assertIn("advertising", keys)
        # cloud peers are NOT blended into retail
        self.assertNotIn("MSFT", r["groups"]["retail"]["tickers"])

    def test_financial_sic_excluded(self):
        self.assertTrue(is_financial_sic(6021))  # commercial bank
        self.assertTrue(is_financial_sic(6798))  # REIT
        self.assertFalse(is_financial_sic(7372))  # software
        self.assertFalse(is_financial_sic(None))

    def test_duplicate_share_class_mapping(self):
        self.assertEqual(DUPLICATE_SHARE_CLASSES["GOOG"], "GOOGL")

    @patch("autoval.peers.get_company_sic")
    def test_unmapped_sic_discovery(self, mock_sic):
        def fake(t, ua):
            sics = {"XYZ": 7372, "AAA": 7372, "BBB": 6021, "CCC": 7372}
            return {"ticker": t, "sic": sics.get(t), "sic_description": "test"}
        mock_sic.side_effect = fake
        r = discover_peers("XYZ", "ua@example.com", candidate_universe=["AAA", "BBB", "CCC"])
        self.assertEqual(r["method"], "sic")
        self.assertEqual(r["sic"], 7372)
        # AAA and CCC (same SIC) discovered; BBB (financial SIC) excluded
        self.assertEqual(r["groups"]["sic_7372"]["tickers"], ["AAA", "CCC"])
        reasons = [e["reason"] for e in r["excluded"]]
        self.assertTrue(any("financial" in r_ for r_ in reasons))


class ScreeningTests(unittest.TestCase):
    def test_screen_peers_insufficient(self):
        peers = {"A": {"market_cap": 1, "ttm_eps": 1, "ttm_ebitda": 1, "ev": 1, "valued": True}}
        r = screen_peers(peers)
        self.assertEqual(len(r["valid"]), 1)  # 1 < 3, caller decides to suppress median

    def test_screen_peers_excludes_invalid(self):
        peers = {
            "A": {"market_cap": 1, "ttm_eps": 1, "ttm_ebitda": 1, "ev": 1, "valued": True},
            "B": {"market_cap": None, "ttm_eps": 1, "ttm_ebitda": 1, "ev": 1, "valued": True},
            "C": {"market_cap": 1, "ttm_eps": -1, "ttm_ebitda": 1, "ev": 1, "valued": False},
        }
        r = screen_peers(peers)
        self.assertEqual(list(r["valid"]), ["A"])


class MissingTargetPriceTests(unittest.TestCase):
    def test_peer_implied_survives_missing_target_price(self):
        from autoval.relative import pe_summary, ev_ebitda_summary
        # implied value uses peer multiples + target fundamentals, NOT the target price
        pe = pe_summary([18.0, 20.0, 22.0], 4.0)
        self.assertIsNotNone(pe["implied_price_median"])
        ev = ev_ebitda_summary([8.0, 9.0, 10.0], 5e9, 10e9, 1e9)
        self.assertIsNotNone(ev["implied_price_median"])


if __name__ == "__main__":
    unittest.main()
