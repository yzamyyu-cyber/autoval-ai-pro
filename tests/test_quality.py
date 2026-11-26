import unittest
from autoval.quality import assess_valuation_quality


def _result(**overrides):
    base = {
        "wacc": 0.10, "terminal_growth": 0.02, "terminal_weight_of_ev": 0.70,
        "shares": 1_000_000_000, "intrinsic_per_share_usd": 100.0,
        "upside_vs_price_pct": -90.0,  # huge gap on purpose: must NOT trigger low-confidence
        "forecast_fcff_usd": [100.0, 110.0, 120.0, 130.0, 140.0],
    }
    result = {
        "mode": "live",
        "analysis": {
            "scenarios": {"base": base},
            "forecast": {"base": {"drivers": {"revenue_growth": 0.10}}},
        },
        "wacc": {"available": True, "wacc": 0.10},
        "provenance": {"financials": {
            "excluded_debt_tags": [],
            "shares": {"tag": "EntityCommonStockSharesOutstanding"},
        }},
        "forecast_history": {"fiscal_years": ["2021", "2022", "2023", "2024", "2025", "2026"]},
    }
    for k, v in overrides.items():
        result[k] = v
    return result


class QualityTests(unittest.TestCase):
    def test_available(self):
        q = assess_valuation_quality(_result())
        self.assertEqual(q["state"], "available")
        self.assertEqual(q["reasons"], [])

    def test_no_price_based_classification(self):
        # a -90% gap must NOT lower confidence (no price-based signal)
        q = assess_valuation_quality(_result())
        self.assertEqual(q["state"], "available")

    def test_low_confidence_debt_reconciliation(self):
        r = _result()
        r["provenance"]["financials"]["excluded_debt_tags"] = [
            {"tag": "LongTermDebtCurrent", "status": "included_in_total", "value_used": 0.0}]
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "low_confidence")
        self.assertTrue(any("debt" in reason.lower() for reason in q["reasons"]))

    def test_low_confidence_wacc_unavailable(self):
        r = _result()
        r["wacc"] = {"available": False, "reason": "down"}
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "low_confidence")
        self.assertTrue(any("wacc" in reason.lower() for reason in q["reasons"]))

    def test_negative_growth_is_warning_not_suppression(self):
        # Negative growth alone is a model-risk warning; it must NOT suppress the valuation.
        r = _result()
        r["analysis"]["forecast"]["base"]["drivers"]["revenue_growth"] = -0.01
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")
        self.assertIn("non-positive", q["model_suitability"][0])
        self.assertTrue(any("growth" in reason.lower() for reason in q["reasons"]))

    def test_terminal_dependence_is_warning_not_suppression(self):
        # Excessive terminal-value dependence is model risk, surfaced as a warning only.
        r = _result()
        r["analysis"]["scenarios"]["base"]["terminal_weight_of_ev"] = 0.90
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")
        self.assertTrue(any("terminal" in reason.lower() for reason in q["model_suitability"]))

    def test_terminal_threshold_is_configurable(self):
        r = _result()
        r["analysis"]["scenarios"]["base"]["terminal_weight_of_ev"] = 0.85
        default = assess_valuation_quality(r)
        self.assertTrue(default["model_suitability"])  # 0.85 > default 0.80
        relaxed = assess_valuation_quality(r, terminal_weight_limit=0.90)
        self.assertEqual(relaxed["model_suitability"], [])  # 0.85 < 0.90

    def test_demo_illustrative_wacc_not_flagged(self):
        # The offline demo intentionally uses an illustrative WACC; that is not a deficiency.
        r = _result()
        r["mode"] = "demo"
        r["wacc"] = None
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")

    def test_unavailable_negative_fcff(self):
        r = _result()
        r["analysis"]["scenarios"]["base"]["forecast_fcff_usd"] = [-10.0, -5.0, -3.0, -2.0, -1.0]
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "unavailable")

    def test_unavailable_no_analysis(self):
        q = assess_valuation_quality({"wacc": {}})
        self.assertEqual(q["state"], "unavailable")

    def test_unsuitable_negative_enterprise_value(self):
        r = _result()
        r["analysis"]["scenarios"]["base"]["enterprise_value_usd"] = -100.0
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "unsuitable")
        self.assertTrue(any("negative enterprise value" in x for x in q["unsuitability"]))

    def test_unsuitable_negative_equity_value(self):
        r = _result()
        r["analysis"]["scenarios"]["base"]["enterprise_value_usd"] = 100.0
        r["analysis"]["scenarios"]["base"]["equity_value_usd"] = -50.0
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "unsuitable")
        self.assertTrue(any("negative equity value" in x for x in q["unsuitability"]))

    def test_weak_fcff_is_warning_not_unsuitable(self):
        # Thin cash-flow margins can be economically valid — warning, not suppression.
        r = _result()
        r["analysis"]["forecast"]["base"]["rows"] = [{"revenue": 10_000.0} for _ in range(5)]
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")
        self.assertEqual(q["unsuitability"], [])
        self.assertTrue(any("thin" in x for x in q["model_suitability"]))

    def test_negative_bear_does_not_invalidate_base(self):
        # A negative bear scenario must not invalidate a defensible (positive) base case.
        r = _result()
        r["analysis"]["scenarios"]["base"]["enterprise_value_usd"] = 100.0
        r["analysis"]["scenarios"]["base"]["equity_value_usd"] = 50.0
        r["analysis"]["scenarios"]["bear"] = {"enterprise_value_usd": -50.0, "equity_value_usd": -80.0}
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")
        self.assertEqual(q["unsuitability"], [])
        self.assertTrue(any("bear" in x for x in q["model_suitability"]))

    def test_inconsistent_reinvestment_is_warning(self):
        r = _result()
        r["analysis"]["forecast"]["base"]["drivers"]["capex_ratio"] = 0.12
        r["analysis"]["forecast"]["base"]["drivers"]["da_ratio"] = 0.03
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "available")  # warning only, not suppression
        self.assertTrue(any("reinvestment" in x.lower() for x in q["model_suitability"]))

    def test_multistage_quality_inherits_source_data_limitations(self):
        from autoval.quality import assess_multistage_quality
        r = _result()
        r["provenance"]["financials"]["excluded_debt_tags"] = [
            {"tag": "LongTermDebtCurrent", "status": "included_in_total", "value_used": 0.0}]
        r["analysis"]["multistage"] = {"base": {
            "terminal_weight_of_ev": 0.5, "enterprise_value_usd": 100.0,
            "equity_value_usd": 50.0, "wacc": 0.10},
            "assumptions": {"mature_incremental_roic": 0.12}}
        q = assess_multistage_quality(r)
        # a new model must not remove unresolved source-data limitations
        self.assertEqual(q["state"], "low_confidence")
        self.assertTrue(any("debt" in x.lower() for x in q["data_quality"]))

    def test_multistage_quality_roic_below_wacc_warns(self):
        from autoval.quality import assess_multistage_quality
        r = _result()
        r["analysis"]["multistage"] = {"base": {
            "terminal_weight_of_ev": 0.5, "enterprise_value_usd": 100.0,
            "equity_value_usd": 50.0, "wacc": 0.12},
            "assumptions": {"mature_incremental_roic": 0.08}}
        q = assess_multistage_quality(r)
        self.assertTrue(any("value-destructive" in x for x in q["model_suitability"]))

    def test_negative_bear_plus_thin_fcff_is_unsuitable(self):
        # Negative downside + persistently thin base FCFF is a material model limitation.
        r = _result()
        r["analysis"]["forecast"]["base"]["rows"] = [{"revenue": 10_000.0} for _ in range(5)]
        r["analysis"]["scenarios"]["base"]["enterprise_value_usd"] = 100.0
        r["analysis"]["scenarios"]["base"]["equity_value_usd"] = 50.0
        r["analysis"]["scenarios"]["bear"] = {"enterprise_value_usd": -50.0, "equity_value_usd": -80.0}
        q = assess_valuation_quality(r)
        self.assertEqual(q["state"], "unsuitable")
        self.assertTrue(any("thin" in x for x in q["unsuitability"]))


if __name__ == "__main__":
    unittest.main()
