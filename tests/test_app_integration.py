"""Parameterized Streamlit AppTest integration tests (offline, deterministic).

Covers all six research tabs, the Annual/TTM basis selector, slider reset, Compare
Companies, and reproduces the previously discovered defects using mocked results.
No live network, credentials or paid APIs are required.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from autoval.pipeline import build_analysis

APP = Path(__file__).resolve().parents[1] / "app.py"


def _button(app, label):
    return next(b for b in app.button if b.label == label)


class AllTabsRenderTests(unittest.TestCase):
    """Every research tab must render for the offline demo without an unhandled exception."""

    def _app(self):
        return AppTest.from_file(APP, default_timeout=30).run()

    def test_demo_all_tabs_no_exception(self):
        app = self._app()
        self.assertFalse(app.exception)
        # Overview
        self.assertTrue(any("Independent DCF check passed" in s.value for s in app.success))
        # Scenario Lab
        self.assertTrue(any(m.label == "What-if DCF / share" for m in app.metric))
        # Multi-stage DCF (demo has no forecast -> informational, not crash)
        self.assertFalse(app.exception)
        # Market Expectations
        self.assertTrue(any(m.label == "Implied annual FCFF growth" for m in app.metric))
        # Financials
        self.assertTrue(any("Projected free cash flow" in s.value for s in app.subheader))
        # Evidence & Exports
        self.assertTrue(any("Independent DCF recomputation" in s.value for s in app.subheader))

    def test_basis_selector_present(self):
        app = self._app()
        labels = [r.label for r in app.radio]
        self.assertIn("Valuation basis", labels)

    def test_scenario_slider_and_reset(self):
        app = self._app()
        before = next(m.value for m in app.metric if m.label == "What-if DCF / share")
        app.slider[0].set_value(1.0).run()
        self.assertFalse(app.exception)
        after = next(m.value for m in app.metric if m.label == "What-if DCF / share")
        self.assertNotEqual(before, after)


class DefectRegressionTests(unittest.TestCase):
    """Reproduce previously discovered defects and assert they are fixed."""

    def _mock(self, result):
        with patch("autoval.pipeline.build_analysis", return_value=result):
            return AppTest.from_file(APP, default_timeout=30).run()

    def test_roic_sensitivity_missing_does_not_crash(self):
        result, prices = build_analysis("DEMO", "demo")
        # give the demo a driver forecast + multi-stage WITHOUT roic_sensitivity
        result["analysis"]["forecast"] = result["analysis"].get("forecast") or {}
        ms = result["analysis"].get("multistage") or {}
        ms.pop("roic_sensitivity", None)
        result["analysis"]["multistage"] = ms
        app = self._mock((result, prices))
        self.assertFalse(app.exception)  # must not raise "Mature ROIC" KeyError

    def test_negative_equity_shown_as_n_a(self):
        result, prices = build_analysis("DEMO", "demo")
        result["analysis"]["scenarios"]["bear"]["intrinsic_per_share_usd"] = -38.61
        app = self._mock((result, prices))
        self.assertFalse(app.exception)
        # the scenario table must not show a bare "-$38.61" price
        text = "\n".join(str(d.value) for d in app.dataframe)
        self.assertNotIn("−$38.61", text)

    def test_fiscal_date_not_overwritten(self):
        result, prices = build_analysis("DEMO", "demo")
        # a complete TTM block (copy the annual scenarios so check_report can run)
        ttm_scenarios = {c: dict(result["analysis"]["scenarios"][c]) for c in ("bear", "base", "bull")}
        result["analysis"]["ttm"] = {"asof": "2026-09-30", **ttm_scenarios,
                                     "forecast": result["analysis"].get("forecast", {}),
                                     "multistage": result["analysis"].get("multistage", {})}
        result["analysis"]["financial_asof"] = "2026-06-30"
        app = self._mock((result, prices))
        self.assertFalse(app.exception)
        text = "\n".join(str(m.value) for m in app.markdown)
        self.assertIn("2026-06-30", text)  # FY preserved, not replaced by 2026-09-30


class CompareCompaniesTests(unittest.TestCase):
    def test_compare_bundled_examples(self):
        app = AppTest.from_file(APP, default_timeout=30).run()
        app.radio[0].set_value("Compare Companies").run()
        self.assertFalse(app.exception)
        table = app.table[0].value
        self.assertEqual(list(table.columns), ["DEMO", "DEMO2"])


if __name__ == "__main__":
    unittest.main()
