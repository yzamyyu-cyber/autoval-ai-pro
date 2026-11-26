"""Deterministic regression tests for the AI Research Analyst (mocked LLM)."""
import json
import unittest

from tests.provider_fixture import build_from_fixture
from autoval.research import (build_report, render_tables, validate_report, _evidence_map,
                              research_cache_key, validate_research_cache_match, deterministic_answer,
                              answer_question, validate_answer_claims)


def _sections(text="narrative"):
    keys = ["executive_summary", "business_and_financial_performance",
            "revenue_growth_profitability_reinvestment", "dcf_interpretation",
            "wacc_and_terminal_assumptions", "comparable_and_reverse_dcf",
            "valuation_drivers_and_sensitivities", "risks_and_limitations",
            "evidence_backed_conclusion"]
    return {k: text for k in keys}


class ResearchTests(unittest.TestCase):
    def _result(self, ticker="MSFT"):
        return build_from_fixture(ticker)[0]

    def test_tables_rendered_from_python(self):
        r = self._result()
        tables = render_tables(r)
        self.assertIn("Intrinsic/share", tables)
        self.assertIn("WACC", tables)

    def test_fabricated_evidence_id_rejected(self):
        r = self._result()
        report = {"ticker": "MSFT", "company": r["company"], "snapshot_id": r["run_utc"],
                  "sections": _sections("[MSFT.fake_metric] claim")}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")
        self.assertTrue(any("fake_metric" in c["reason"] for c in v["checks"]))

    def test_wrong_company_rejected(self):
        r = self._result("MSFT")
        report = {"ticker": "AAPL", "company": r["company"], "snapshot_id": r["run_utc"],
                  "sections": _sections("")}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")

    def test_api_failure_graceful(self):
        def boom(messages):
            raise RuntimeError("LLM down")
        r = self._result()
        report = build_report(r, chat_fn=boom)
        self.assertIn("error", report.get("sections", {}))

    def test_build_report_with_mock(self):
        r = self._result()
        report = build_report(r, chat_fn=lambda m: json.dumps(_sections("text")))
        self.assertIn("Executive summary", report["markdown"])
        self.assertIn("Financial tables", report["markdown"])

    def test_unsupported_headline_suppressed(self):
        # low-confidence valuation must not allow a fabricated headline price.
        r = self._result()
        r["quality"] = {"state": "low_confidence"}
        report = {"ticker": "MSFT", "company": r["company"], "snapshot_id": r["run_utc"],
                  "sections": _sections("conclusion: worth $999 per share")}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")

    def test_incorrect_value_on_valid_citation_rejected(self):
        r = self._result()
        emap = _evidence_map(r)
        eid = next(iter(emap))
        report = {"ticker": "MSFT", "company": r["company"], "snapshot_id": r["run_utc"],
                  "sections": _sections("text"),
                  "claims": [{"evidence_id": eid, "metric": emap[eid]["metric"],
                              "value": (emap[eid]["value"] or 0) + 99_999_999}]}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")
        self.assertTrue(any("value mismatch" in c["reason"] for c in v["checks"]))

    def test_stale_snapshot_rejected(self):
        r = self._result()
        report = {"ticker": "MSFT", "company": r["company"], "snapshot_id": "stale-snapshot-id",
                  "sections": _sections("text")}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")

    def test_percentage_scaling(self):
        # upside_vs_price_pct is already a percentage; must NOT be re-scaled by 100.
        r = self._result()
        tables = render_tables(r)
        self.assertIn("%", tables)
        self.assertNotIn("-8560", tables)  # no double-scaling (e.g. -85.6% shown as -8560%)

    def test_missing_evidence_rejected(self):
        r = self._result()
        report = {"ticker": "MSFT", "company": r["company"], "snapshot_id": r["run_utc"],
                  "sections": _sections("text"),
                  "claims": [{"evidence_id": "MSFT.nonexistent", "metric": "x", "value": 1}]}
        v = validate_report(report, r)
        self.assertEqual(v["status"], "rejected")


class ResearchAppTests(unittest.TestCase):
    def _r(self):
        return build_from_fixture("MSFT")[0]

    def test_research_tab_renders(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        APP = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(APP, default_timeout=40).run()
        self.assertFalse(app.exception)
        text = "\n".join(str(s.value) for s in app.subheader)
        self.assertIn("AI Research Analyst", text)

    def test_cache_key_changes_on_basis_switch(self):
        r = self._r()
        r["valuation_basis"] = "annual"
        k1 = research_cache_key(r)
        r2 = self._r(); r2["valuation_basis"] = "ttm"
        k2 = research_cache_key(r2)
        self.assertNotEqual(k1["basis"], k2["basis"])
        self.assertFalse(validate_research_cache_match(k1, k2))

    def test_cache_key_changes_on_assumption_change(self):
        r = self._r()
        k1 = research_cache_key(r)
        k2 = dict(k1)
        k2["drivers"] = dict(k1["drivers"]); k2["drivers"]["capex_ratio"] = 0.99
        self.assertFalse(validate_research_cache_match(k1, k2))

    def test_deterministic_answer(self):
        r = self._r()
        self.assertIsNotNone(deterministic_answer("wacc", r)["answer"])
        self.assertIsNotNone(deterministic_answer("revenue", r)["answer"])
        self.assertIsNone(deterministic_answer("unrelated", r)["answer"])

    def test_answer_question_mocked_valid(self):
        import json as _j
        r = self._r()
        emap = _evidence_map(r)
        eid = next(iter(emap)); val = emap[eid]["value"]
        def fake(messages):
            return _j.dumps({"answer": "ok", "claims": [{"evidence_id": eid, "metric": emap[eid]["metric"], "value": val}], "sources": [eid]})
        a = answer_question(r, "what is X?", chat_fn=fake)
        self.assertEqual(a["validation"]["status"], "validated")

    def test_answer_question_rejects_fabricated_claim(self):
        import json as _j
        r = self._r()
        emap = _evidence_map(r)
        eid = next(iter(emap))
        def fake(messages):
            return _j.dumps({"answer": "ok", "claims": [{"evidence_id": eid, "value": 999_999_999}], "sources": []})
        a = answer_question(r, "q", chat_fn=fake)
        self.assertEqual(a["validation"]["status"], "rejected")

    def test_answer_question_provider_failure(self):
        def boom(messages):
            raise RuntimeError("down")
        r = self._r()
        a = answer_question(r, "q", chat_fn=boom)
        self.assertIn("error", a)


if __name__ == "__main__":
    unittest.main()
