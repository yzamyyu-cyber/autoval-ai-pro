import unittest
from unittest.mock import patch
from autoval.wacc import (
    cost_of_equity, after_tax_cost_of_debt, capital_weights, wacc, beta_ols, compute_wacc
)
from autoval.finance import sensitivity_table, derive_scenarios


class WaccPureTests(unittest.TestCase):
    def test_cost_of_equity(self):
        self.assertAlmostEqual(cost_of_equity(0.04, 1.2, 0.05), 0.10)

    def test_after_tax_cost_of_debt(self):
        self.assertAlmostEqual(after_tax_cost_of_debt(0.05, 0.21), 0.0395)

    def test_after_tax_cost_of_debt_invalid_tax(self):
        with self.assertRaises(ValueError):
            after_tax_cost_of_debt(0.05, 1.5)

    def test_capital_weights(self):
        we, wd = capital_weights(900, 100)
        self.assertAlmostEqual(we, 0.9)
        self.assertAlmostEqual(wd, 0.1)

    def test_wacc(self):
        w, we, wd = wacc(900, 100, 0.10, 0.04)
        self.assertAlmostEqual(w, 0.9 * 0.10 + 0.1 * 0.04)

    def test_compute_wacc(self):
        r = compute_wacc(0.04, 1.2, 0.05, 900, 100, 0.05, 0.21)
        self.assertAlmostEqual(r["cost_of_equity"], 0.10)
        self.assertAlmostEqual(r["after_tax_cost_of_debt"], 0.0395)
        self.assertAlmostEqual(r["wacc"], 0.9 * 0.10 + 0.1 * 0.0395)

    def test_beta_ols_recovers_known_beta(self):
        x = [0.01, -0.02, 0.03, -0.01, 0.005, 0.02, -0.015, 0.01]
        y = [1.5 * xi + 0.001 for xi in x]
        r = beta_ols(x, y)
        self.assertAlmostEqual(r["beta"], 1.5, places=6)
        self.assertAlmostEqual(r["r_squared"], 1.0, places=6)
        self.assertEqual(r["n"], len(x))

    def test_beta_ols_needs_observations(self):
        with self.assertRaises(ValueError):
            beta_ols([0.01], [0.02])

    def test_tnx_unit_scaling(self):
        from autoval.wacc_data import _tnx_to_decimal
        # Yahoo ^TNX reports a percent yield: 4.998 == 4.998% -> 0.04998
        self.assertAlmostEqual(_tnx_to_decimal(4.998), 0.04998)
        self.assertAlmostEqual(_tnx_to_decimal(3.75), 0.0375)


class SensitivityTests(unittest.TestCase):
    def test_sensitivity_grid(self):
        tbl = sensitivity_table(100, 10, 0, 0.05, [0.10, 0.12], [0.02, 0.03])
        self.assertEqual(len(tbl), 4)  # 2 wacc x 2 terminal g
        for row in tbl:
            self.assertGreater(row["wacc"], row["terminal_growth"])
            self.assertGreater(row["intrinsic_per_share_usd"], 0)

    def test_derive_scenarios_company_wacc_single_rate(self):
        h = [100, 110, 121]
        p = derive_scenarios(h, wacc=0.09)
        self.assertEqual(p["bear"]["wacc"], 0.09)
        self.assertEqual(p["base"]["wacc"], 0.09)
        self.assertEqual(p["bull"]["wacc"], 0.09)

    def test_derive_scenarios_illustrative(self):
        h = [100, 110, 121]
        p = derive_scenarios(h)
        self.assertEqual(p["bear"]["wacc"], 0.11)
        self.assertEqual(p["base"]["wacc"], 0.10)
        self.assertEqual(p["bull"]["wacc"], 0.09)

    def test_derive_scenarios_wacc_gt_terminal_guard(self):
        h = [100, 110, 121]
        with self.assertRaises(ValueError):
            derive_scenarios(h, wacc=0.02)  # below bull terminal growth 2.5%

    def test_analysis_wacc_fields_for_dashboard(self):
        from autoval.finance import analyze_valuation
        stock = {
            "ticker": "X", "market_price": 100.0, "shares": 10, "net_debt": 20,
            "diluted_shares": 11,
            "fcff_history": [
                {"year_end": "2023-12-31", "fcff_usd": 100},
                {"year_end": "2024-12-31", "fcff_usd": 110},
                {"year_end": "2025-12-31", "fcff_usd": 121},
            ],
            "total_debt": 50, "cash_and_equivalents": 30,
        }
        a = analyze_valuation(stock, wacc=0.09)
        self.assertEqual(a["wacc_basis"], "company-specific")
        self.assertEqual(len(a["sensitivity"]), 15)  # 5 WACC x 3 terminal growth
        self.assertEqual(a["shares_outstanding"], 10)
        self.assertEqual(a["diluted_shares"], 11)
        ws = {a["scenarios"][c]["wacc"] for c in ("bear", "base", "bull")}
        self.assertEqual(len(ws), 1)
        self.assertAlmostEqual(ws.pop(), 0.09)
        for row in a["sensitivity"]:
            self.assertGreater(row["wacc"], row["terminal_growth"])


class WaccDataTests(unittest.TestCase):
    def _stock(self):
        return {"market_price": 100.0, "shares": 10, "total_debt": 50,
                "balance_sheet_asof": "2026-09-30", "financial_asof": "2026-06-30",
                "share_count_asof": "2026-10-22",
                "source": {"annual_records": [{"interest": {"value": 2.0}}]}}

    def test_build_company_wacc_available(self):
        from autoval.wacc_data import build_company_wacc
        with patch("autoval.wacc_data.fetch_risk_free_rate", return_value={"available": True, "value": 0.04}):
            with patch("autoval.wacc_data.fetch_erp", return_value={"available": True, "value": 0.05}):
                with patch("autoval.wacc_data.fetch_beta", return_value={"available": True, "value": 1.1}):
                    r = build_company_wacc("MSFT", self._stock())
        self.assertTrue(r["available"])
        self.assertAlmostEqual(r["wacc"], r["calculation"]["wacc"])
        self.assertGreater(r["wacc"], 0)
        # internally-assembled inputs carry a data-classification "kind"
        for key in ("equity_value", "debt_value", "pre_tax_cost_of_debt", "marginal_tax_rate"):
            self.assertIn("kind", r["inputs"][key])

    def test_build_company_wacc_missing_input_unavailable(self):
        from autoval.wacc_data import build_company_wacc
        with patch("autoval.wacc_data.fetch_risk_free_rate", return_value={"available": False, "value": None, "reason": "down"}):
            with patch("autoval.wacc_data.fetch_erp", return_value={"available": True, "value": 0.05}):
                with patch("autoval.wacc_data.fetch_beta", return_value={"available": True, "value": 1.1}):
                    r = build_company_wacc("MSFT", self._stock())
        self.assertFalse(r["available"])
        self.assertIn("risk_free_rate", r["reason"])


if __name__ == "__main__":
    unittest.main()
