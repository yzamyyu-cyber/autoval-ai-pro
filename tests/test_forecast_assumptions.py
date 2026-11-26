"""Deterministic regression tests for evidence-backed forecast assumptions (mocked LLM)."""
import unittest

from tests.provider_fixture import build_from_fixture
from autoval.forecast_assumptions import (
    investigate_assumptions, validate_assumptions, apply_assumptions, _current_drivers,
)


def _prop(driver, proposed, **kw):
    p = {"driver": driver, "proposed": proposed, "source": "10-K MD&A",
         "filing_date": "2026-07-30", "kind": "guidance", "justification": "x",
         "horizon": "FY2027", "uncertainty": "y"}
    p.update(kw)
    return p


class ValidateAssumptionsTests(unittest.TestCase):
    def _result(self):
        return build_from_fixture("MSFT")[0]

    def test_valid_guidance_validated(self):
        r = self._result()
        v = validate_assumptions([_prop("capex_intensity", [0.25, 0.30])], r)
        self.assertEqual(v["status"], "validated")

    def test_invalid_range_rejected(self):
        r = self._result()
        v = validate_assumptions([_prop("operating_margin", 1.5)], r)
        self.assertEqual(v["status"], "rejected")

    def test_unsupported_driver_rejected(self):
        r = self._result()
        v = validate_assumptions([_prop("market_share", 0.5)], r)
        self.assertEqual(v["status"], "rejected")

    def test_missing_source_rejected(self):
        r = self._result()
        v = validate_assumptions([_prop("revenue_growth", 0.2, source="")], r)
        self.assertEqual(v["status"], "rejected")

    def test_stale_evidence_rejected(self):
        # filing_date postdates the analysis snapshot -> look-ahead.
        r = self._result()
        r["run_utc"] = "2026-06-30T00:00:00Z"
        v = validate_assumptions([_prop("capex_intensity", 0.3, filing_date="2026-07-30")], r)
        self.assertEqual(v["status"], "rejected")
        self.assertTrue(any("look-ahead" in c["reason"] for c in v["checks"]))


class ApplyAssumptionsTests(unittest.TestCase):
    def _result(self):
        return build_from_fixture("MSFT")[0]

    def test_apply_preserves_wacc_and_terminal(self):
        r = self._result()
        before = r["analysis"]["scenarios"]["base"]
        out = apply_assumptions(r, [_prop("capex_intensity", 0.30)])
        after = out["result"]["analysis"]["scenarios"]["base"]
        self.assertEqual(after["wacc"], before["wacc"])  # WACC preserved
        self.assertEqual(after["terminal_growth"], before["terminal_growth"])  # terminal preserved

    def test_apply_changes_capex_dcf(self):
        r = self._result()
        out = apply_assumptions(r, [_prop("capex_intensity", 0.30)])
        self.assertNotEqual(out["before"]["base"], out["after"]["base"])

    def test_apply_unauthorized_driver_ignored(self):
        # transition/mature ROIC changes require separate approval; here capex only.
        r = self._result()
        out = apply_assumptions(r, [_prop("capex_intensity", 0.30)])
        self.assertNotIn("mature_incremental_roic", out["overrides"])

    def test_temporary_capex_horizon_fades(self):
        # A temporary CapEx ELEVATION must fade over its horizon, not persist into perpetuity.
        r = self._result()
        persist = apply_assumptions(r, [_prop("capex_intensity", 0.45, horizon="5 years")])
        temp = apply_assumptions(r, [_prop("capex_intensity", 0.45, horizon="2 years")])
        # temporary horizon -> less negative (fade to lower capex) than persistent elevation
        self.assertGreater(temp["after"]["base"], persist["after"]["base"])


class InvestigateAssumptionsTests(unittest.TestCase):
    def test_investigate_mocked(self):
        import json
        r = build_from_fixture("MSFT")[0]
        def fake(messages):
            return json.dumps({"proposals": [_prop("capex_intensity", [0.25, 0.30])]})
        out = investigate_assumptions(r, "", chat_fn=fake)
        self.assertEqual(len(out["proposals"]), 1)
        self.assertEqual(out["proposals"][0]["driver"], "capex_intensity")


if __name__ == "__main__":
    unittest.main()
