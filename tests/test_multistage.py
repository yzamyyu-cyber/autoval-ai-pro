import unittest
from autoval.forecast import build_forecast
from autoval.multistage import (multistage_dcf, multistage_valuation,
                                implied_reinvestment_rate)


def _history():
    return {
        "revenue": [168, 198, 212, 245, 282, 332],
        "operating_income": [70, 83, 89, 109, 126, 147],
        "da": [11, 15, 14, 21, 28, 44],
        "capex": [21, 24, 28, 44, 65, 116],
        "nwc": [-16, -17, -18, -21, -21, -33],
        "effective_tax_rate": [0.14, 0.13, 0.19, 0.18, 0.18, 0.19],
    }


class MultistageFormulaTests(unittest.TestCase):
    def test_terminal_reinvestment_rate_is_g_over_roic(self):
        d = multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=0.12)
        self.assertAlmostEqual(d["reinvestment_rate_terminal"], 0.02 / 0.12, places=6)

    def test_terminal_fcff_formula(self):
        d = multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=0.12)
        t = d["terminal"]
        # FCFF = NOPAT_11 × (1 − g/ROIC)
        self.assertAlmostEqual(t["fcff_usd"], t["nopat_usd"] * (1 - 0.02 / 0.12), places=6)
        # TV = FCFF / (WACC − g)
        self.assertAlmostEqual(t["terminal_value_usd"], t["fcff_usd"] / (0.10 - 0.02), places=6)

    def test_explicit_years_preserved(self):
        fc = build_forecast(_history())
        d = multistage_dcf(fc, 0.10, 0.02)
        explicit = d["explicit_rows"]
        self.assertEqual(len(explicit), 5)
        for i, row in enumerate(explicit):
            self.assertEqual(row["fcff"], fc["base"]["rows"][i]["fcff"])

    def test_transition_monotonic_growth(self):
        d = multistage_dcf(build_forecast(_history()), 0.10, 0.02)
        g = [r["revenue_growth"] for r in d["transition_rows"]]
        self.assertEqual(len(g), 5)
        # growth fades monotonically toward terminal growth
        self.assertGreater(g[0], g[-1])
        self.assertAlmostEqual(g[-1], 0.02, places=6)
        # reinvestment fades monotonically toward g/ROIC
        r = [x["reinvestment_rate"] for x in d["transition_rows"]]
        self.assertGreater(r[0], r[-1])
        self.assertAlmostEqual(r[-1], 0.02 / 0.12, places=6)

    def test_valuation_equity_bridge(self):
        fc = build_forecast(_history())
        v = multistage_valuation(fc, 0.10, 0.02, net_debt=100, shares=10)
        self.assertAlmostEqual(v["intrinsic_per_share_usd"],
                               (v["enterprise_value_usd"] - 100) / 10, places=6)
        self.assertEqual(v["equity_value_usd"], v["enterprise_value_usd"] - 100)

    def test_negative_equity_preserved_not_zeroed(self):
        fc = build_forecast(_history())
        v = multistage_valuation(fc, 0.10, 0.02, net_debt=1e12, shares=10)
        self.assertLess(v["equity_value_usd"], 0)
        self.assertLess(v["intrinsic_per_share_usd"], 0)

    def test_higher_roic_lowers_reinvestment_raises_fcff(self):
        # A higher mature ROIC needs less reinvestment for the same growth, so terminal FCFF is higher.
        low = multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=0.08)
        high = multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=0.20)
        self.assertGreater(low["reinvestment_rate_terminal"], high["reinvestment_rate_terminal"])
        self.assertLess(low["terminal"]["fcff_usd"], high["terminal"]["fcff_usd"])


class MultistageValidationTests(unittest.TestCase):
    def test_roic_must_exceed_terminal_growth(self):
        with self.assertRaisesRegex(ValueError, "must exceed terminal growth"):
            multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=0.01)

    def test_wacc_must_exceed_terminal_growth(self):
        with self.assertRaisesRegex(ValueError, "terminal growth"):
            multistage_dcf(build_forecast(_history()), 0.02, 0.03)

    def test_roic_in_range(self):
        for bad in (0.0, 1.0, 1.5, -0.1):
            with self.assertRaisesRegex(ValueError, "ROIC"):
                multistage_dcf(build_forecast(_history()), 0.10, 0.02, mature_incremental_roic=bad)

    def test_transition_years_positive_int(self):
        with self.assertRaisesRegex(ValueError, "transition"):
            multistage_dcf(build_forecast(_history()), 0.10, 0.02, transition_years=0)

    def test_implied_reinvestment_rate_formula(self):
        row = {"nopat": 100, "capex": 60, "da": 20, "change_in_nwc": 10}
        self.assertAlmostEqual(implied_reinvestment_rate(row), (60 - 20 + 10) / 100)


class MultistageIndependentVerificationTests(unittest.TestCase):
    def test_independent_decimal_recomputation(self):
        from verify_output import check_multistage
        fc = build_forecast(_history())
        ms = {}
        for case, tg in (("bear", 0.015), ("base", 0.020), ("bull", 0.025)):
            ms[case] = multistage_valuation(fc, 0.10, tg, 100, 10, case=case)
        result = check_multistage({"analysis": {"multistage": ms}})
        self.assertTrue(result["available"])
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["checks"]), 3)

    def test_missing_multistage_is_unavailable(self):
        from verify_output import check_multistage
        result = check_multistage({"analysis": {}})
        self.assertFalse(result["available"])
        self.assertFalse(result["passed"])


class MultistageRoicSensitivityTests(unittest.TestCase):
    def test_roic_sensitivity_values(self):
        from autoval.multistage import multistage_roic_sensitivity
        fc = build_forecast(_history())
        rows = multistage_roic_sensitivity(fc, 0.10, 0.02, 100, 10)
        self.assertEqual([r["mature_incremental_roic"] for r in rows],
                         [0.08, 0.10, 0.12, 0.15, 0.20])
        vals = {r["mature_incremental_roic"]: r["intrinsic_per_share_usd"]
                for r in rows if r["valid"]}
        # higher ROIC -> higher terminal FCFF -> higher value
        self.assertLess(vals[0.08], vals[0.20])

    def test_roic_sensitivity_skips_roic_below_terminal_growth(self):
        from autoval.multistage import multistage_roic_sensitivity
        fc = build_forecast(_history())
        rows = multistage_roic_sensitivity(fc, 0.10, 0.02, 100, 10,
                                           roic_values=(0.01, 0.12))
        self.assertFalse(rows[0]["valid"])  # 1% < 2% terminal growth
        self.assertTrue(rows[1]["valid"])


if __name__ == "__main__":
    unittest.main()
