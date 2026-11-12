import unittest
from unittest.mock import patch
import pandas as pd
from autoval.market import fetch_market


class MarketTests(unittest.TestCase):
    @patch("yfinance.Ticker")
    def test_empty_data_raises(self, MockTicker):
        MockTicker.return_value.history.return_value = pd.DataFrame()
        with self.assertRaisesRegex(ValueError, "no daily close prices"):
            fetch_market("MSFT")

    @patch("yfinance.Ticker")
    def test_short_history_raises(self, MockTicker):
        idx = pd.bdate_range("2024-01-01", periods=100)
        MockTicker.return_value.history.return_value = pd.DataFrame(
            {"Close": list(range(100)), "Adj Close": list(range(100))}, index=idx)
        with self.assertRaisesRegex(ValueError, "201 daily"):
            fetch_market("MSFT")

    @patch("yfinance.Ticker")
    def test_valid_history_returns_dict(self, MockTicker):
        idx = pd.bdate_range("2024-01-01", periods=250)
        MockTicker.return_value.history.return_value = pd.DataFrame(
            {"Close": list(range(250)), "Adj Close": list(range(250))}, index=idx)
        out = fetch_market("MSFT")
        self.assertIn("market_price", out)
        self.assertIn("price_date", out)
        self.assertIn("close_prices", out)
        self.assertEqual(len(out["close_prices"]), 250)
        self.assertEqual(out["market_price"], 249.0)


if __name__ == "__main__":
    unittest.main()
