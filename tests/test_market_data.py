import unittest
from autoval.market_data import classify_market_data, is_genuine, classify_wacc, resolve_market


class MarketResolutionTests(unittest.TestCase):
    """Provider failure must default to 'missing'; only explicit selection yields illustrative/saved."""

    def test_provider_failure_defaults_to_missing(self):
        def boom(ticker):
            raise RuntimeError("network down")
        source, mode, closes, price, price_date = resolve_market("MSFT", "", boom)
        self.assertEqual(mode, "missing")
        self.assertEqual(source["mode"], "missing")
        self.assertEqual(source["classification"], "missing market data")
        self.assertIsNone(price)
        self.assertIsNone(price_date)
        self.assertEqual(len(closes), 0)

    def test_genuine_fetch_yields_current(self):
        def ok(ticker):
            return {"market_source": {"mode": "current", "provider": "Yahoo Finance",
                                      "price_date": "2026-11-25"},
                    "close_prices": __import__("pandas").Series([1.0, 2.0]),
                    "market_price": 255.39, "price_date": "2026-11-25"}
        source, mode, closes, price, price_date = resolve_market("MSFT", "", ok)
        self.assertEqual(mode, "current")
        self.assertEqual(price, 255.39)
        self.assertEqual(price_date, "2026-11-25")
        self.assertEqual(len(closes), 2)

    def test_explicit_illustrative_stores_no_genuine_price(self):
        source, mode, closes, price, price_date = resolve_market("MSFT", "illustrative", None)
        self.assertEqual(mode, "illustrative")
        self.assertIsNone(price)          # hypothetical price never stored as market_price
        self.assertIsNone(price_date)
        self.assertEqual(len(closes), 0)

    def test_explicit_saved_with_dated_snapshot_is_genuine(self):
        source, mode, closes, price, price_date = resolve_market(
            "MSFT", "saved", None, saved_price=533.16, saved_price_date="2026-11-10")
        self.assertEqual(mode, "saved")
        self.assertEqual(price, 533.16)
        self.assertEqual(price_date, "2026-11-10")
        self.assertEqual(source["mode"], "saved")
        self.assertEqual(len(closes), 0)

    def test_explicit_saved_without_snapshot_is_missing_not_fabricated(self):
        source, mode, closes, price, price_date = resolve_market("MSFT", "saved", None)
        self.assertEqual(mode, "missing")
        self.assertIsNone(price)
        self.assertIsNone(price_date)
        self.assertEqual(source["classification"], "missing market data")


def _history():
    return {
        "revenue": [168, 198, 212, 245, 282, 332],
        "operating_income": [70, 83, 89, 109, 126, 147],
        "da": [11, 15, 14, 21, 28, 44],
        "capex": [21, 24, 28, 44, 65, 116],
        "nwc": [-16, -17, -18, -21, -21, -33],
    }


class MarketDataPolicyTests(unittest.TestCase):
    def test_current_requires_provenance(self):
        src = {"mode": "current", "provider": "Yahoo Finance", "price_date": "2026-11-25",
               "retrieved_at": "2026-11-25T00:00:00Z"}
        self.assertEqual(classify_market_data(src, 255.39), "current")

    def test_label_alone_not_trusted(self):
        # a bare "current" label without provider/date/price is NOT current
        self.assertEqual(classify_market_data({"mode": "current"}, None), "missing")

    def test_saved_snapshot(self):
        src = {"mode": "saved", "price_date": "2026-11-10"}
        self.assertEqual(classify_market_data(src, 533.16), "saved")

    def test_illustrative(self):
        self.assertEqual(classify_market_data({"mode": "illustrative"}, 100.0), "illustrative")

    def test_placeholder_price_not_current(self):
        # a placeholder price (mode illustrative) must not be treated as genuine
        self.assertFalse(is_genuine("illustrative"))
        self.assertFalse(is_genuine("missing"))

    def test_is_genuine(self):
        self.assertTrue(is_genuine("current"))
        self.assertTrue(is_genuine("saved"))

    def test_wacc_classification(self):
        self.assertEqual(classify_wacc({"available": True}, beta_available=True, equity_available=True),
                         "company-specific")
        self.assertEqual(classify_wacc({"available": True}, beta_available=False, equity_available=True),
                         "illustrative")
        self.assertEqual(classify_wacc({"available": False}, True, True), "unavailable")
        self.assertEqual(classify_wacc(None, True, True), "unavailable")


class BackendMarketDataTests(unittest.TestCase):
    """The production DCF must null market-price fields when the price is hypothetical."""

    def test_illustrative_price_nulls_market_fields(self):
        from autoval.finance import analyze_driver_valuation
        stock = {"ticker": "X", "market_price": None, "price_date": None,
                 "shares": 10, "net_debt": 100}
        val = analyze_driver_valuation(stock, _history())
        self.assertIsNone(val["market_price"])
        for case in val["scenarios"].values():
            self.assertIsNone(case["upside_vs_price_pct"])
            # forward DCF still computes an intrinsic value
            self.assertIsNotNone(case["intrinsic_per_share_usd"])

    def test_genuine_price_100_still_valid(self):
        from autoval.finance import analyze_driver_valuation
        stock = {"ticker": "X", "market_price": 100.0, "price_date": "2026-11-25",
                 "shares": 10, "net_debt": 100}
        val = analyze_driver_valuation(stock, _history())
        self.assertEqual(val["market_price"], 100.0)
        base = val["scenarios"]["base"]
        self.assertAlmostEqual(base["upside_vs_price_pct"],
                               (base["intrinsic_per_share_usd"] / 100.0 - 1) * 100)


if __name__ == "__main__":
    unittest.main()
