import unittest
from decimal import Decimal
from unittest.mock import patch
from autoval.forecast import project_fcff, derive_scenario_drivers, build_forecast
from autoval.finance import dcf_from_fcff


class ForecastFormulaTests(unittest.TestCase):
    def test_project_fcff_formula(self):
        rows = project_fcff(1000, 100, 2, 0.10, 0.20, 0.21, 0.05, 0.10, 0.15)
        r = rows[0]
        self.assertAlmostEqual(r["revenue"], 1100)
        self.assertAlmostEqual(r["ebit"], 220)
        self.assertAlmostEqual(r["nopat"], 220 * 0.79)
        self.assertAlmostEqual(r["da"], 55)
        self.assertAlmostEqual(r["capex"], 110)
        self.assertAlmostEqual(r["nwc"], 165)
        self.assertAlmostEqual(r["change_in_nwc"], 65)  # 165 - 100
        self.assertAlmostEqual(r["fcff"], 220 * 0.79 + 55 - 110 - 65)

    def test_nwc_increase_reduces_fcff(self):
        hi = project_fcff(1000, 100, 1, 0.10, 0.20, 0.21, 0.05, 0.10, 0.20)
        lo = project_fcff(1000, 100, 1, 0.10, 0.20, 0.21, 0.05, 0.10, 0.10)
        # higher NWC ratio -> larger increase in NWC -> lower FCFF
        self.assertLess(hi[0]["fcff"], lo[0]["fcff"])
        self.assertGreater(hi[0]["change_in_nwc"], lo[0]["change_in_nwc"])

    def test_capex_negative_guard(self):
        with self.assertRaises(ValueError):
            project_fcff(1000, 100, 1, 0.10, 0.20, 0.21, 0.05, -0.10, 0.15)

    def test_tax_rate_range_guard(self):
        with self.assertRaises(ValueError):
            project_fcff(1000, 100, 1, 0.10, 0.20, 1.5, 0.05, 0.10, 0.15)

    def test_independent_decimal_verification(self):
        rows = project_fcff(1000, 100, 1, 0.10, 0.20, 0.21, 0.05, 0.10, 0.15)
        r = rows[0]
        D = Decimal
        rev = D("1000") * (D("1") + D("0.10"))
        ebit = rev * D("0.20")
        nopat = ebit * (D("1") - D("0.21"))
        da = rev * D("0.05")
        capex = rev * D("0.10")
        nwc = rev * D("0.15")
        d_nwc = nwc - D("100")
        fcff = nopat + da - capex - d_nwc
        self.assertAlmostEqual(float(fcff), r["fcff"], places=9)


class ScenarioDriverTests(unittest.TestCase):
    def _history(self):
        return {
            "revenue": [168, 198, 212, 245, 282, 332],
            "operating_income": [70, 83, 89, 109, 126, 147],
            "da": [11, 15, 14, 21, 28, 44],
            "capex": [21, 24, 28, 44, 65, 116],
            "nwc": [-40],
            "effective_tax_rate": [0.14, 0.13, 0.19, 0.18, 0.18, 0.19],
        }

    def test_driver_ordering(self):
        d = derive_scenario_drivers(self._history())
        self.assertLess(d["bear"]["revenue_growth"], d["base"]["revenue_growth"])
        self.assertLess(d["base"]["revenue_growth"], d["bull"]["revenue_growth"])
        self.assertLess(d["bear"]["operating_margin"], d["base"]["operating_margin"])
        self.assertLess(d["base"]["operating_margin"], d["bull"]["operating_margin"])
        self.assertGreater(d["bear"]["capex_ratio"], d["bull"]["capex_ratio"])

    def test_same_normalized_tax_across_scenarios(self):
        d = derive_scenario_drivers(self._history())
        t = {d[c]["normalized_tax_rate"] for c in ("bear", "base", "bull")}
        self.assertEqual(len(t), 1)
        self.assertEqual(t.pop(), 0.21)

    def test_build_forecast_structure(self):
        f = build_forecast(self._history(), years=5)
        self.assertEqual(set(f), {"bear", "base", "bull"})
        for case, obj in f.items():
            self.assertEqual(len(obj["rows"]), 5)
            self.assertIn("fcff", obj["rows"][0])


class DcfFromFcffTests(unittest.TestCase):
    def test_basic(self):
        d = dcf_from_fcff([100, 100, 100, 100, 100], 10, 0, 0.10, 0.02)
        self.assertGreater(d["enterprise_value_usd"], 0)
        self.assertAlmostEqual(d["intrinsic_per_share_usd"], d["equity_value_usd"] / 10)
        self.assertAlmostEqual(d["terminal_weight_of_ev"],
                               d["pv_terminal_value_usd"] / d["enterprise_value_usd"])

    def test_wacc_gt_terminal_guard(self):
        with self.assertRaises(ValueError):
            dcf_from_fcff([100, 100, 100, 100, 100], 10, 0, 0.02, 0.03)

    def test_empty_stream_guard(self):
        with self.assertRaises(ValueError):
            dcf_from_fcff([], 10, 0, 0.10, 0.02)


class RetrieveHistoryTests(unittest.TestCase):
    def _facts(self):
        from tests.test_sec import annual, instant
        x = {"facts": {"us-gaap": {}, "dei": {}}}
        u = x["facts"]["us-gaap"]
        ends = ["2024-12-31", "2025-12-31", "2026-12-31"]
        u["RevenueFromContractWithCustomerExcludingAssessedTax"] = {"units": {"USD": [annual(v, e) for v, e in zip([100, 120, 144], ends)]}}
        u["OperatingIncomeLoss"] = {"units": {"USD": [annual(v, e) for v, e in zip([20, 26, 32], ends)]}}
        u["PaymentsToAcquirePropertyPlantAndEquipment"] = {"units": {"USD": [annual(v, e) for v, e in zip([10, 12, 15], ends)]}}
        u["Depreciation"] = {"units": {"USD": [annual(v, e) for v, e in zip([5, 6, 7], ends)]}}
        u["AmortizationOfIntangibleAssets"] = {"units": {"USD": [annual(v, e) for v, e in zip([1, 1, 1], ends)]}}
        u["IncomeTaxExpenseBenefit"] = {"units": {"USD": [annual(v, e) for v, e in zip([4, 5, 6], ends)]}}
        u["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"] = {"units": {"USD": [annual(v, e) for v, e in zip([25, 31, 38], ends)]}}
        u["AccountsReceivableNetCurrent"] = {"units": {"USD": [instant(30, "2026-12-31")]}}
        u["AccountsPayableCurrent"] = {"units": {"USD": [instant(15, "2026-12-31")]}}
        return x

    @patch("autoval.forecast_data.fetch_json")
    @patch("autoval.forecast_data.sec_lookup", return_value=(123, "Mock Co"))
    def test_retrieve_history(self, _lookup, fetch):
        from autoval.forecast_data import retrieve_history
        fetch.side_effect = [self._facts()]
        h = retrieve_history("MOCK", "Example example@example.com")
        self.assertEqual(h["revenue"], [100, 120, 144])
        self.assertEqual(h["operating_income"], [20, 26, 32])
        self.assertEqual(h["da"], [6, 7, 8])  # 5+1, 6+1, 7+1
        self.assertEqual(h["capex"], [10, 12, 15])
        self.assertAlmostEqual(h["nwc_latest"], 15)  # 30 - 15

    @patch("autoval.forecast_data.fetch_json")
    @patch("autoval.forecast_data.sec_lookup", return_value=(123, "Mock Co"))
    def test_insufficient_history_raises(self, _lookup, fetch):
        from autoval.forecast_data import retrieve_history
        from tests.test_sec import annual
        x = {"facts": {"us-gaap": {}}}
        u = x["facts"]["us-gaap"]
        u["RevenueFromContractWithCustomerExcludingAssessedTax"] = {"units": {"USD": [annual(100, "2026-12-31")]}}
        u["OperatingIncomeLoss"] = {"units": {"USD": [annual(20, "2026-12-31")]}}
        u["PaymentsToAcquirePropertyPlantAndEquipment"] = {"units": {"USD": [annual(10, "2026-12-31")]}}
        fetch.side_effect = [x]
        with self.assertRaisesRegex(ValueError, "at least 2 years"):
            retrieve_history("MOCK", "Example example@example.com")


class CapexSensitivityTests(unittest.TestCase):
    def _history(self):
        return {
            "revenue": [168, 198, 212, 245, 282, 332],
            "operating_income": [70, 83, 89, 109, 126, 147],
            "da": [11, 15, 14, 21, 28, 44],
            "capex": [21, 24, 28, 44, 65, 116],
            "nwc": [-16, -17, -18, -21, -21, -33],
            "effective_tax_rate": [0.14, 0.13, 0.19, 0.18, 0.18, 0.19],
        }

    def test_capex_stats(self):
        from autoval.forecast import capex_stats
        s = capex_stats(self._history())
        self.assertAlmostEqual(s["fy_latest"], 116 / 332, places=4)
        self.assertIsNotNone(s["three_year_mean"])
        self.assertIsNotNone(s["six_year_mean"])
        self.assertIsNotNone(s["six_year_median"])

    def test_higher_capex_reduces_fcff(self):
        from autoval.forecast import forecast_with_capex, build_forecast
        base = build_forecast(self._history())
        high = forecast_with_capex(self._history(), 0.349)
        for case in ("bear", "base", "bull"):
            base_fcff = sum(r["fcff"] for r in base[case]["rows"])
            high_fcff = sum(r["fcff"] for r in high[case])
            self.assertLess(high_fcff, base_fcff)  # higher capex intensity -> lower FCFF

    def test_nwc_none_handling(self):
        from autoval.forecast import derive_scenario_drivers
        h = self._history()
        h["nwc"] = [None, None, None, -21, -21, -33]
        d = derive_scenario_drivers(h)
        # last non-None NWC (-33) / last revenue (332) = -9.94%
        self.assertAlmostEqual(d["base"]["nwc_ratio"], -33 / 332, places=4)


if __name__ == "__main__":
    unittest.main()
