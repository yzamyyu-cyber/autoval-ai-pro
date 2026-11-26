"""Parameterized AppTest matrix over seven deterministic ticker fixtures.

Each ticker is processed by the PRODUCTION valuation on a sanitized fixture (no live
network, no pre-rendered results), then the full Streamlit app is exercised and the
displayed company identity / financial period / DCF values are asserted.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.provider_fixture import build_from_fixture

APP = Path(__file__).resolve().parents[1] / "app.py"
TICKERS = ("MSFT", "AMZN", "AAPL", "HD", "GOOGL", "TSLA", "NVDA")


class SevenCompanyMatrixTests(unittest.TestCase):
    def _app(self, ticker):
        result, prices = build_from_fixture(ticker)
        with patch("autoval.pipeline.build_analysis", return_value=(result, prices)):
            return AppTest.from_file(APP, default_timeout=40).run(), result

    def test_all_seven_companies_render(self):
        for t in TICKERS:
            with self.subTest(ticker=t):
                app, result = self._app(t)
                self.assertFalse(app.exception, f"{t} raised an unhandled exception")
                # company identity displayed
                text = "\n".join(str(m.value) for m in app.markdown)
                self.assertIn(result["company"].split(" ")[0], text, f"{t} company not shown")

    def test_financial_period_displayed(self):
        for t in TICKERS:
            with self.subTest(ticker=t):
                app, result = self._app(t)
                text = "\n".join(str(m.value) for m in app.markdown)
                fy = str(result["analysis"].get("financial_asof") or "")
                self.assertIn(fy, text, f"{t} fiscal period not shown")

    def test_market_price_displayed(self):
        for t in TICKERS:
            with self.subTest(ticker=t):
                app, result = self._app(t)
                self.assertFalse(app.exception)
                text = "\n".join(str(m.value) for m in app.markdown)
                price = result["analysis"]["market_price"]
                self.assertIn(f"{price:,.2f}", text, f"{t} market price not shown")

    def test_dcf_values_displayed(self):
        for t in TICKERS:
            with self.subTest(ticker=t):
                app, result = self._app(t)
                self.assertFalse(app.exception)
                text = "\n".join(str(d.value) for d in app.dataframe)
                self.assertIn("DCF", text, f"{t} DCF tables not shown")

    def test_nvda_newer_results_notice(self):
        app, result = self._app("NVDA")
        self.assertFalse(app.exception)
        self.assertTrue(any("Newer results available" in w.value for w in app.warning),
                        "NVDA must show the newer-results freshness notice")

    def test_freshness_preserved_across_basis_switch(self):
        app, result = self._app("NVDA")
        self.assertFalse(app.exception)
        # the notice must still be present after toggling basis (radio index 1 = valuation basis)
        text = "\n".join(str(w.value) for w in app.warning)
        self.assertIn("Newer results available", text)


if __name__ == "__main__":
    unittest.main()
