from copy import deepcopy
from decimal import Decimal
import unittest

from autoval.pipeline import build_analysis
from autoval.reverse import reverse_dcf


def reference_price(first_fcff, growth, years, wacc, terminal, net_debt, shares):
    """Calculate the target independently using Decimal dollars and rates."""
    first, g, w, t, debt, count = (Decimal(str(v)) for v in
                                  (first_fcff, growth, wacc, terminal, net_debt, shares))
    first_pv = first / (1 + w)
    ratio = (1 + g) / (1 + w)
    explicit_pv = first_pv * (1 - ratio ** years) / (1 - ratio) if ratio != 1 else first_pv * years
    terminal_pv = first_pv * ratio ** (years - 1) * (1 + t) / (w - t)
    return float((explicit_pv + terminal_pv - debt) / count)


class ReverseDcfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo, _ = build_analysis()

    def test_recovers_known_growth_for_offline_demo(self):
        base = self.demo["analysis"]["scenarios"]["base"]
        result = reverse_dcf(self.demo, base["intrinsic_per_share_usd"])
        self.assertAlmostEqual(result["implied_fcff_growth"], base["growth"], places=8)
        self.assertAlmostEqual(result["base_forecast_fcff_cagr"], base["growth"], places=8)

    def test_recovers_independent_known_growth_on_another_forecast(self):
        fixture = {
            "ticker": "FICT",
            "mode": "demo",
            "analysis": {
                "market_price": reference_price(25e6, .13, 4, .11, .025, -3e6, 2e6),
                "scenarios": {"base": {
                    "wacc": .11, "terminal_growth": .025, "net_debt_usd": -3e6, "shares": 2e6,
                    "forecast_fcff_usd": [25e6, 26e6, 29e6, 30e6],
                }},
            },
        }
        result = reverse_dcf(fixture)
        self.assertAlmostEqual(result["implied_fcff_growth"], .13, places=8)
        self.assertAlmostEqual(result["base_forecast_fcff_cagr"], 1.2 ** (1 / 3) - 1, places=8)
        self.assertLess(abs(result["price_error_usd"]), .01)

    def test_synthetic_price_matches_independent_repricing(self):
        result = reverse_dcf(self.demo)
        calculated = reference_price(
            result["first_year_fcff_usd"], result["implied_fcff_growth"], result["forecast_years"],
            result["wacc"], result["terminal_growth"], result["net_debt_usd"], result["shares"],
        )
        self.assertAlmostEqual(calculated, 145.0, places=2)
        self.assertEqual(result["price_date"], "2026-10-30")

    def test_higher_hypothetical_price_requires_higher_growth(self):
        baseline = reverse_dcf(self.demo)
        changed = reverse_dcf(self.demo, 170)
        self.assertGreater(changed["implied_fcff_growth"], baseline["implied_fcff_growth"])
        self.assertEqual(changed["target_source"], "user input")
        self.assertIsNone(changed["price_date"])

    def test_reports_target_outside_search_range(self):
        with self.assertRaisesRegex(ValueError, "No match within"):
            reverse_dcf(self.demo, 1e8)

    def test_requires_positive_cash_flow_anchor_and_target(self):
        fixture = deepcopy(self.demo)
        fixture["analysis"]["scenarios"]["base"]["forecast_fcff_usd"][0] = 0
        with self.assertRaisesRegex(ValueError, "positive year-one FCFF"):
            reverse_dcf(fixture)
        with self.assertRaisesRegex(ValueError, "positive year-one FCFF"):
            reverse_dcf(self.demo, 0)

    def test_allows_missing_comparison_when_base_ending_cash_flow_is_negative(self):
        fixture = deepcopy(self.demo)
        fixture["analysis"]["scenarios"]["base"]["forecast_fcff_usd"][-1] = -1
        self.assertIsNone(reverse_dcf(fixture)["base_forecast_fcff_cagr"])
