"""Production-pipeline acceptance for the four market-data modes (offline, deterministic).

Monkeypatches only the network boundaries and drives the REAL `build_analysis` live path
through all four conditions, asserting the market-data integrity policy end-to-end.
"""
import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

from autoval.pipeline import build_analysis

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "MSFT.json")


def _fx():
    with open(FIXTURE) as f:
        return json.load(f)


def _genuine_market(price=533.16, date="2026-11-10"):
    closes = pd.Series([100.0 + i * 0.01 for i in range(250)],
                       index=pd.bdate_range("2025-01-01", periods=250), name="close")
    return {"market_price": price, "price_date": date, "close_prices": closes,
            "market_source": {"provider": "test provider", "price_date": date,
                              "mode": "current", "classification": "current"}}


def _company_wacc(available=True, beta_available=True, equity_available=True):
    wacc = {"available": available, "wacc": 0.098, "calculation": {},
            "inputs": {
                "risk_free_rate": {"available": True, "value": 0.05, "period": "fixture"},
                "equity_risk_premium": {"available": True, "value": 0.0446, "period": "fixture"},
                "beta": {"available": beta_available, "value": 1.12, "period": "fixture"},
                "equity_value": {"available": equity_available, "value": 1e12},
                "debt_value": {"available": True, "value": 1e11},
                "pre_tax_cost_of_debt": {"available": True, "value": 0.03},
                "marginal_tax_rate": {"available": True, "value": 0.21},
            }}
    return wacc


class _LivePipeline:
    """Context manager monkeypatching the network boundaries of build_analysis(live)."""

    def __init__(self, fetch=None):
        self.fetch = fetch  # callable(ticker) -> market dict, or raises

    def __enter__(self):
        fx = _fx()
        self.patches = [
            patch("autoval.sec.get_sec_financials", return_value=fx["stock"]),
            patch("autoval.forecast_data.retrieve_history", return_value=fx["history"]),
            patch("autoval.wacc_data.build_company_wacc", return_value=_company_wacc()),
            patch("autoval.peers.peer_groups", return_value={}),
            patch("autoval.freshness.check_freshness", return_value={"status": "up-to-date"}),
        ]
        if self.fetch is not None:
            self.patches.append(patch("autoval.pipeline.fetch_market", self.fetch))
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


class PipelineMarketModeTests(unittest.TestCase):
    def test_current_mode_is_genuine(self):
        with _LivePipeline(fetch=lambda t: _genuine_market()):
            result, _ = build_analysis("MSFT", "live", "test@example.com")
        self.assertEqual(result["market_mode"], "current")
        self.assertIsNotNone(result["analysis"]["market_price"])
        self.assertIsNotNone(result["analysis"]["price_date"])

    def test_provider_failure_defaults_to_missing(self):
        def boom(t):
            raise RuntimeError("network down")
        with _LivePipeline(fetch=boom):
            result, _ = build_analysis("MSFT", "live", "test@example.com")
        self.assertEqual(result["market_mode"], "missing")
        self.assertIsNone(result["analysis"]["market_price"])
        self.assertIsNone(result["analysis"]["price_date"])
        # forward DCF still computes intrinsic value (financials are genuine)
        base = result["analysis"]["scenarios"]["base"]
        self.assertIsNotNone(base["intrinsic_per_share_usd"])
        self.assertIsNone(base["upside_vs_price_pct"])
        # no market cap derived from a placeholder price
        self.assertIsNone(result["multiples"]["market_enterprise_value_usd"])

    def test_explicit_illustrative_never_claims_genuine_price(self):
        with _LivePipeline(fetch=lambda t: _genuine_market()):
            result, _ = build_analysis("MSFT", "live", "test@example.com",
                                       market_mode="illustrative", illustrative_price=200.0)
        self.assertEqual(result["market_mode"], "illustrative")
        self.assertIsNone(result["analysis"]["market_price"])  # hypothetical NOT genuine
        self.assertEqual(result["illustrative_market_price"], 200.0)  # stored separately
        self.assertIsNone(result["analysis"]["scenarios"]["base"]["upside_vs_price_pct"])

    def test_explicit_saved_is_genuine_dated(self):
        with _LivePipeline(fetch=lambda t: _genuine_market()):
            result, _ = build_analysis("MSFT", "live", "test@example.com",
                                       market_mode="saved", saved_price=500.0,
                                       saved_price_date="2026-10-31")
        self.assertEqual(result["market_mode"], "saved")
        self.assertEqual(result["analysis"]["market_price"], 500.0)
        self.assertEqual(result["analysis"]["price_date"], "2026-10-31")
        base = result["analysis"]["scenarios"]["base"]
        self.assertIsNotNone(base["upside_vs_price_pct"])

    def test_wacc_basis_reflects_provenance(self):
        # Missing market price -> equity_value unavailable -> WACC not company-specific.
        def boom(t):
            raise RuntimeError("network down")
        with _LivePipeline(fetch=boom):
            with patch("autoval.wacc_data.build_company_wacc",
                       return_value=_company_wacc(available=False, beta_available=True,
                                                  equity_available=False)):
                result, _ = build_analysis("MSFT", "live", "test@example.com")
        self.assertEqual(result["wacc_basis"], "unavailable")

    def test_reverse_dcf_gated_on_genuine_mode(self):
        from autoval.reverse import reverse_dcf
        def boom(t):
            raise RuntimeError("network down")
        with _LivePipeline(fetch=boom):
            result, _ = build_analysis("MSFT", "live", "test@example.com")
        with self.assertRaisesRegex(ValueError, "genuine market observation"):
            reverse_dcf(result)


if __name__ == "__main__":
    unittest.main()
