import unittest

from autoval.finance import analyze_driver_valuation
from autoval.pipeline import build_analysis
from autoval.relative import summarize_relative_valuation
from autoval.report import build_report_markdown
from autoval.wacc import compute_wacc


class ReportTests(unittest.TestCase):
    def _demo(self):
        r, _ = build_analysis("DEMO", "demo")
        return r

    def _full_report(self):
        result = self._demo()
        stock = {
            "ticker": "DEMO", "market_price": 145, "price_date": "2026-10-30",
            "shares": 1e9, "net_debt": 12e9, "total_debt": 20e9, "cash_and_equivalents": 8e9,
        }
        history = {
            "asof": "2025-12-31",
            "revenue": [100e9, 110e9, 120e9],
            "operating_income": [25e9, 27.5e9, 30e9],
            "da": [6e9, 6.6e9, 7.2e9],
            "capex": [10e9, 11e9, 24e9],
            "nwc": [8e9],
        }
        wacc = compute_wacc(.04, 1.2, .05, 145e9, 20e9, .07, .21)
        result["wacc"] = {"available": True, "calculation": wacc}
        result["analysis"] = analyze_driver_valuation(stock, history, wacc["wacc"])
        target = {"ttm_eps": 10, "ttm_ebitda": 25e9, "ttm_diluted_shares": 1e9}
        peers = {
            ticker: {"ticker": ticker, "pe": pe, "ev_ebitda": 13, "valued": True}
            for ticker, pe in (("A", 18), ("B", 19.74), ("C", 22))
        }
        groups = {"core": ["A", "B", "C"], "supplemental": ["A"]}
        result["relative"] = {"target": target, "groups": summarize_relative_valuation(target, peers, groups)}
        return result

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
        self.assertIn("Peer estimates are unavailable", md)

    def test_full_report_has_all_sections(self):
        md = build_report_markdown(self._full_report())
        for section in ("Valuation summary", "DCF (Base case)", "Company-specific WACC",
                        "Sensitivity", "CapEx sensitivity", "Five-year forecast",
                        "Relative valuation", "Sources & limitations"):
            self.assertIn(section, md)

    def test_report_contains_values(self):
        md = build_report_markdown(self._full_report())
        self.assertIn("Fictional Example Holdings", md)
        self.assertIn("not investment advice", md)
        self.assertIn("Fictional reference price", md)

    def test_report_download_content_is_markdown(self):
        md = build_report_markdown(self._full_report())
        self.assertTrue(md.startswith("# "))

    def test_capex_sensitivity_values_distinct(self):
        result = self._full_report()
        base = result["analysis"]["scenarios"]["base"]["intrinsic_per_share_usd"]
        stress = result["analysis"]["capex_sensitivity"]["intrinsic_per_share_usd"]["base"]
        self.assertLess(stress, base)
        md = build_report_markdown(result)
        self.assertIn(f"Base CapEx intensity 13.3% → Base intrinsic ${base:,.2f}", md)
        self.assertIn(f"Persistent high CapEx 20.0% → Base intrinsic ${stress:,.2f}", md)

    def test_n1_groups_labeled_single_observation(self):
        # supplemental/cloud groups are n=1 -> must be labeled, not shown as a median
        md = build_report_markdown(self._full_report())
        self.assertIn("insufficient valid peers", md)

    def test_report_pe_uses_multiple_convention(self):
        # P/E must be a multiple (19.7x), not a percentage (1974%)
        md = build_report_markdown(self._full_report())
        self.assertIn("19.7x", md)
        self.assertNotIn("1974%", md)


if __name__ == "__main__":
    unittest.main()
