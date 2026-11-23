import csv
from decimal import Decimal
import io
import unittest
from autoval.pipeline import build_analysis
from autoval.compare import comparison_rows, comparability_flags, comparison_csv, extract_comparison


class CompareTests(unittest.TestCase):
    def _demo(self):
        return build_analysis("DEMO", "demo")[0]

    def _demo2(self):
        return build_analysis("DEMO2", "demo")[0]

    def test_extract_comparison_fields(self):
        c = extract_comparison(self._demo())
        for f in ("ticker", "company", "mode", "price", "price_date", "financial_asof",
                  "base_dcf_per_share", "intrinsic_price_gap_usd", "valuation_gap_pct",
                  "wacc", "forecast_growth", "forecast_growth_basis"):
            self.assertIn(f, c)
        self.assertEqual(c["ticker"], "DEMO")
        self.assertEqual(c["mode"], "demo")
        self.assertEqual(c["forecast_growth_basis"], "FCFF (constant-growth)")

    def test_valuation_gap_recomputed(self):
        r = self._demo()
        c = extract_comparison(r)
        price = r["analysis"]["market_price"]
        intrinsic = r["analysis"]["scenarios"]["base"]["intrinsic_per_share_usd"]
        self.assertAlmostEqual(c["intrinsic_price_gap_usd"], intrinsic - price, places=6)
        self.assertAlmostEqual(c["valuation_gap_pct"], (intrinsic / price - 1) * 100, places=6)

    def test_two_distinct_companies(self):
        rows = comparison_rows([self._demo(), self._demo2()])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ticker"], "DEMO")
        self.assertEqual(rows[1]["ticker"], "DEMO2")
        self.assertNotEqual(rows[0]["base_dcf_per_share"], rows[1]["base_dcf_per_share"])

    def test_no_flags_when_same_dates(self):
        rows = comparison_rows([self._demo(), self._demo2()])
        self.assertEqual(comparability_flags(rows), [])

    def test_flag_when_mixed_modes(self):
        d = self._demo()
        live = dict(d)
        live["mode"] = "live"
        live["ticker"] = "LIVE"
        rows = comparison_rows([d, live])
        self.assertTrue(any("mode" in f.lower() for f in comparability_flags(rows)))

    def test_csv_headers_and_rows(self):
        text = comparison_csv([self._demo(), self._demo2()])
        first, second = csv.DictReader(io.StringIO(text))
        self.assertEqual(first["ticker"], "DEMO")
        self.assertEqual(second["ticker"], "DEMO2")
        price = Decimal(first["price"])
        intrinsic = Decimal(first["base_dcf_per_share"])
        self.assertAlmostEqual(Decimal(first["intrinsic_price_gap_usd"]), intrinsic - price, places=10)
        self.assertAlmostEqual(Decimal(first["valuation_gap_pct"]), (intrinsic / price - 1) * 100, places=10)
        self.assertEqual(first["median_pe"], "")
        self.assertNotEqual(first["forecast_growth"], first["implied_fcff_growth"])

    def test_second_demo_price_history_matches_its_reference(self):
        report, prices = build_analysis("DEMO2", "demo")
        self.assertAlmostEqual(prices["close"].iloc[-1], report["analysis"]["market_price"])

    def test_flags_different_dates_and_growth_measures(self):
        first = extract_comparison(self._demo())
        second = extract_comparison(self._demo2())
        second.update(price_date="2026-10-29", forecast_growth_basis="Revenue (driver)")
        flags = comparability_flags([first, second])
        self.assertTrue(any("Price dates differ" in flag for flag in flags))
        self.assertTrue(any("Forecast growth measures differ" in flag for flag in flags))


if __name__ == "__main__":
    unittest.main()
