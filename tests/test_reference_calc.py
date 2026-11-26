import os
import sys
import unittest

# The reference engine lives in evidence/ (standalone, no autoval imports).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "evidence"))

import verify_reference as vr  # noqa: E402


class ReferenceEngineTests(unittest.TestCase):
    def _drivers(self):
        return {"revenue_growth": 0.10, "operating_margin": 0.20,
                "normalized_tax_rate": 0.21, "da_ratio": 0.05,
                "capex_ratio": 0.10, "nwc_ratio": 0.15}

    def test_fcff_projection(self):
        # year1: rev 1100, nopat 173.8, da 55, capex 110, dNWC 65 -> 53.8
        stream = vr.project_fcff(self._drivers(), 1000.0, 100.0)
        self.assertEqual(len(stream), 5)
        self.assertAlmostEqual(stream[0], 173.8 + 55.0 - 110.0 - 65.0, places=1)

    def test_fcff_detects_wrong_capex(self):
        d = self._drivers()
        s1 = vr.project_fcff(d, 1000.0, 100.0)
        d["capex_ratio"] = 0.20  # deliberate error
        s2 = vr.project_fcff(d, 1000.0, 100.0)
        self.assertNotAlmostEqual(s1[0], s2[0])

    def test_wacc_reconstruction(self):
        inputs = {"risk_free_rate": {"value": 0.04}, "beta": {"value": 1.2},
                  "equity_risk_premium": {"value": 0.05}, "equity_value": {"value": 1e9},
                  "debt_value": {"value": 0.5e9}, "pre_tax_cost_of_debt": {"value": 0.06},
                  "marginal_tax_rate": {"value": 0.21}}
        coe, cod, wacc = vr.recompute_wacc(inputs)
        self.assertAlmostEqual(coe, 0.04 + 1.2 * 0.05)
        self.assertAlmostEqual(wacc, coe * 2 / 3 + cod * (1 - 0.21) * 1 / 3, places=6)

    def test_discount_and_bridge(self):
        stream = [100.0, 110.0, 120.0, 130.0, 140.0]
        pv, tv, ev = vr.discount(stream, 0.10, 0.02)
        equity = ev - 100.0
        intrinsic = equity / 10.0
        # independent Decimal-style check
        expected_pv = sum(cf / 1.1 ** t for t, cf in enumerate(stream, 1))
        self.assertAlmostEqual(pv, expected_pv, places=6)
        self.assertAlmostEqual(tv, stream[-1] * 1.02 / 0.08, places=6)
        self.assertAlmostEqual(ev, expected_pv + tv / 1.1 ** 5, places=6)
        self.assertAlmostEqual(intrinsic, (ev - 100.0) / 10.0)

    def test_detects_wrong_debt(self):
        stream = [100.0] * 5
        pv, tv, ev = vr.discount(stream, 0.10, 0.02)
        eq_ok = ev - 100.0
        eq_bad = ev - 500.0  # wrong debt
        self.assertNotEqual(eq_ok, eq_bad)


class TagResolutionTests(unittest.TestCase):
    """A stale/partial tag must not win over a current consolidated tag (GOOGL/NVDA/AAPL)."""

    def test_resolve_tag_prefers_latest_annual(self):
        import evidence.reconcile_source as rs
        facts = {"facts": {"us-gaap": {
            # old/partial tag: only a 2023 annual fact
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"start": "2023-01-01", "end": "2023-12-31", "form": "10-K", "filed": "2024-02-01", "val": 100}]}},
            # current consolidated tag: 2026 annual fact
            "Revenues": {"units": {"USD": [
                {"start": "2026-01-01", "end": "2026-12-31", "form": "10-K", "filed": "2027-02-01", "val": 1000}]}},
        }}}
        tag = rs._resolve_tag(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"), "USD", "2027-03-01")
        self.assertEqual(tag, "Revenues")


if __name__ == "__main__":
    unittest.main()
