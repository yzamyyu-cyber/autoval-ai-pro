"""AppTest for the AI Financial Reconciliation section (deterministic, offline).

The investigation button is not clicked here (it would hit the live LLM/SEC); this test
verifies the section renders detected issues and the proposal display paths without an
unhandled exception, and that a clean analysis shows the "no issues" message.
"""
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from autoval.pipeline import build_analysis

APP = Path(__file__).resolve().parents[1] / "app.py"


def _issue_result():
    result, prices = build_analysis("DEMO", "demo")
    fin = dict(result["provenance"]["financials"])
    fin["excluded_debt_tags"] = [
        {"tag": "CommercialPaper", "status": "stale_nonzero",
         "last_end": "2026-06-30", "last_value": 4_837_000_000}]
    fin["debt_reconciliation"] = {"reference_date": "2026-09-30",
                                  "net_debt": None, "total_debt": None,
                                  "cash_and_equivalents": 15_365_000_000}
    fin["long_debt"] = {"tag": "LongTermDebtNoncurrent", "value": 21_897_000_000}
    result["provenance"]["financials"] = fin
    result["ticker"] = "PG"
    return result, prices


class ReconciliationUITests(unittest.TestCase):
    def test_section_renders_detected_issue(self):
        result, prices = _issue_result()
        with patch("autoval.pipeline.build_analysis", return_value=(result, prices)):
            app = AppTest.from_file(APP, default_timeout=40).run()
        self.assertFalse(app.exception)
        subheaders = "\n".join(str(s.value) for s in app.subheader)
        text = "\n".join(str(m.value) for m in app.markdown)
        self.assertIn("AI Financial Reconciliation", subheaders)
        self.assertIn("Detected issue", text)
        self.assertIn("debt_component_stale_nonzero", text)

    def test_clean_analysis_shows_no_issues(self):
        result, prices = build_analysis("DEMO", "demo")
        with patch("autoval.pipeline.build_analysis", return_value=(result, prices)):
            app = AppTest.from_file(APP, default_timeout=40).run()
        self.assertFalse(app.exception)
        infos = "\n".join(str(i.value) for i in app.info)
        self.assertIn("No reconciliation issues detected", infos)


if __name__ == "__main__":
    unittest.main()
