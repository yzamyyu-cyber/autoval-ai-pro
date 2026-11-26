import unittest

from app import apply_basis


def _result():
    return {
        "analysis": {
            "financial_asof": "2026-06-30",  # latest completed FY (annual)
            "scenarios": {"bear": {}, "base": {}, "bull": {}},
            "forecast": {"base": {}},
            "multistage": {
                "base": {}, "bear": {}, "bull": {},
                "roic_sensitivity": [{"valid": True, "mature_incremental_roic": 0.12,
                                      "reinvestment_rate_terminal": 0.167,
                                      "intrinsic_per_share_usd": 100.0}],
                "assumptions": {"mature_incremental_roic": 0.12},
            },
            "ttm": {
                "asof": "2026-09-30",
                "bear": {}, "base": {}, "bull": {},
                "forecast": {"base": {}},
                "multistage": {
                    "base": {}, "bear": {}, "bull": {},
                    "roic_sensitivity": [{"valid": True, "mature_incremental_roic": 0.12,
                                          "reinvestment_rate_terminal": 0.167,
                                          "intrinsic_per_share_usd": 90.0}],
                    "assumptions": {"mature_incremental_roic": 0.12},
                },
            },
        },
    }


class BasisSwitchingTests(unittest.TestCase):
    def test_ttm_preserves_financial_asof(self):
        r = apply_basis(_result(), "ttm")
        # the latest completed FY must NOT be overwritten with the TTM period
        self.assertEqual(r["analysis"]["financial_asof"], "2026-06-30")
        self.assertEqual(r["valuation_basis"], "ttm")
        self.assertEqual(r["valuation_basis_asof"], "2026-09-30")

    def test_ttm_multistage_has_roic_sensitivity(self):
        r = apply_basis(_result(), "ttm")
        self.assertIn("roic_sensitivity", r["analysis"]["multistage"])
        self.assertTrue(r["analysis"]["multistage"]["roic_sensitivity"])

    def test_annual_returns_unchanged(self):
        res = _result()
        r = apply_basis(res, "annual")
        self.assertIs(r, res)  # annual basis returns the same object unchanged
        self.assertEqual(r["analysis"]["financial_asof"], "2026-06-30")

    def test_ttm_without_ttm_data_returns_unchanged(self):
        r = apply_basis({"analysis": {"financial_asof": "2025-12-31", "scenarios": {}}}, "ttm")
        self.assertEqual(r["analysis"]["financial_asof"], "2025-12-31")


if __name__ == "__main__":
    unittest.main()
