import unittest
import json
from autoval.pipeline import build_analysis
from autoval.report import build_report_markdown


class ReportTests(unittest.TestCase):
    def _demo(self):
        r, _ = build_analysis("DEMO", "demo")
        return r

    def _msft(self):
        return json.load(open("outputs/workswarm_msft_v8/analysis.json"))

    def test_demo_report_generates(self):
        md = build_report_markdown(self._demo())
        self.assertIn("Equity Research Report", md)
        self.assertIn("Valuation summary", md)
        self.assertIn("Bear", md)
        self.assertIn("not investment advice", md)

    def test_demo_handles_missing_optional(self):
        # DEMO has no bridge / forecast / relative / wacc — must not raise
        md = build_report_markdown(self._demo())
        self.assertIn("Company-specific WACC unavailable", md)
        self.assertIn("Not available (no peer group", md)

    def test_msft_report_has_all_sections(self):
        md = build_report_markdown(self._msft())
        for section in ("Valuation summary", "DCF (Base case)", "Company-specific WACC",
                        "Sensitivity", "CapEx sensitivity", "Five-year forecast",
                        "Relative valuation", "Sources & limitations"):
            self.assertIn(section, md)

    def test_report_contains_values(self):
        md = build_report_markdown(self._msft())
        self.assertIn("MICROSOFT", md.upper())
        self.assertIn("not investment advice", md)
        self.assertIn("Market close", md)

    def test_report_download_content_is_markdown(self):
        md = build_report_markdown(self._msft())
        self.assertTrue(md.startswith("# "))

    def test_capex_sensitivity_values_distinct(self):
        # Regression: base-capEx and high-capEx lines must show DIFFERENT intrinsic values
        md = build_report_markdown(self._msft())
        self.assertIn("Base CapEx intensity 25.3% → Base intrinsic $235.25", md)
        self.assertIn("Persistent high CapEx 34.9% → Base intrinsic $137.40", md)

    def test_n1_groups_labeled_single_observation(self):
        # supplemental/cloud groups are n=1 -> must be labeled, not shown as a median
        md = build_report_markdown(self._msft())
        self.assertIn("single/limited observation", md)

    def test_report_pe_uses_multiple_convention(self):
        # P/E must be a multiple (19.7x), not a percentage (1974%)
        md = build_report_markdown(self._msft())
        self.assertIn("19.7x", md)
        self.assertNotIn("1974%", md)


if __name__ == "__main__":
    unittest.main()
