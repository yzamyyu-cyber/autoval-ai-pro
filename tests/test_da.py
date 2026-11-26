"""Deterministic regression tests for the accounting-aware D&A resolver."""
import unittest

from autoval.da import resolve_annual_da, resolve_ttm_da

YEARS = ["2024-01-31", "2025-01-31", "2026-01-31"]


def _annual(val, end, filed="2026-03-15"):
    y = int(end[:4])
    return {"start": f"{y - 1}-02-01", "end": end, "form": "10-K", "filed": filed, "val": val}


def _fy(val, end, filed="2026-03-15"):
    """A ~1-year 10-K fact with a start date one year before the fiscal year-end."""
    from datetime import date, timedelta
    d = date.fromisoformat(end) - timedelta(days=365)
    return {"start": d.isoformat(), "end": end, "form": "10-K", "filed": filed, "val": val}


def _facts(us_gaap):
    return {"facts": {"us-gaap": us_gaap, "dei": {}}}


def _tag(val, end):
    return {"units": {"USD": [_annual(val, end)]}}


class AnnualDaResolverTests(unittest.TestCase):
    def test_prefers_consolidated_total_over_lease_component(self):
        # WMT-like: consolidated total present AND a lease-amortization component present.
        us = {
            "DepreciationAmortizationAndAccretionNet": {"units": {"USD": [
                _annual(11.853e9, "2024-01-31"), _annual(12.973e9, "2025-01-31"),
                _annual(14.203e9, "2026-01-31")]}},
            "FinanceLeaseRightOfUseAssetAmortization": {"units": {"USD": [
                _annual(0.7e9, "2024-01-31"), _annual(0.8e9, "2025-01-31"),
                _annual(0.9e9, "2026-01-31")]}},
        }
        r = resolve_annual_da(_facts(us), YEARS)
        self.assertEqual(r["status"], "consolidated")
        # total is used, NOT the lease component alone
        self.assertAlmostEqual(r["values"]["2026-01-31"], 14.203e9, places=0)
        self.assertEqual(r["detail"][-1]["tag"], "DepreciationAmortizationAndAccretionNet")

    def test_component_only_reconstruction(self):
        us = {
            "Depreciation": {"units": {"USD": [_annual(10e9, "2024-01-31"),
                                              _annual(11e9, "2025-01-31"),
                                              _annual(12e9, "2026-01-31")]}},
            "AmortizationOfIntangibleAssets": {"units": {"USD": [_annual(1e9, "2024-01-31"),
                                                                 _annual(1e9, "2025-01-31"),
                                                                 _annual(1e9, "2026-01-31")]}},
        }
        r = resolve_annual_da(_facts(us), YEARS)
        self.assertEqual(r["status"], "derived")
        self.assertAlmostEqual(r["values"]["2026-01-31"], 13e9, places=0)

    def test_lease_amortization_alone_is_unavailable(self):
        # Only the finance-lease amortization component present -> must NOT be used as D&A.
        us = {"FinanceLeaseRightOfUseAssetAmortization": {"units": {"USD": [
            _annual(0.9e9, "2024-01-31"), _annual(0.9e9, "2025-01-31"),
            _annual(0.9e9, "2026-01-31")]}}}
        r = resolve_annual_da(_facts(us), YEARS)
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["values"], {})

    def test_no_double_count_total_and_components(self):
        # Consolidated total present alongside components: total is used, not sum+components.
        us = {
            "DepreciationDepletionAndAmortization": {"units": {"USD": [
                _annual(12e9, "2024-01-31"), _annual(12e9, "2025-01-31"),
                _annual(12e9, "2026-01-31")]}},
            "Depreciation": {"units": {"USD": [_annual(11e9, "2024-01-31"),
                                               _annual(11e9, "2025-01-31"),
                                               _annual(11e9, "2026-01-31")]}},
        }
        r = resolve_annual_da(_facts(us), YEARS)
        self.assertEqual(r["status"], "consolidated")
        self.assertAlmostEqual(r["values"]["2026-01-31"], 12e9, places=0)

    def test_incomplete_component_coverage_unavailable(self):
        # Depreciation present for only 2 of 3 years -> reconstruction incomplete.
        us = {"Depreciation": {"units": {"USD": [_annual(10e9, "2024-01-31"),
                                                 _annual(11e9, "2025-01-31")]}}}
        r = resolve_annual_da(_facts(us), YEARS)
        self.assertEqual(r["status"], "unavailable")

    def test_cross_period_tag_migration_merge(self):
        # NKE-like: Depreciation (older years) + DepreciationDepletionAndAmortization
        # (newer years) with equal overlap -> merged into a complete series.
        years = ["2021-05-31", "2022-05-31", "2023-05-31", "2024-05-31",
                 "2025-05-31", "2026-05-31"]
        us = {
            "Depreciation": {"units": {"USD": [
                _fy(744e6, "2021-05-31"), _fy(717e6, "2022-05-31"),
                _fy(703e6, "2023-05-31"), _fy(796e6, "2024-05-31")]}},
            "DepreciationDepletionAndAmortization": {"units": {"USD": [
                _fy(703e6, "2023-05-31"), _fy(796e6, "2024-05-31"),
                _fy(775e6, "2025-05-31"), _fy(747e6, "2026-05-31")]}},
        }
        r = resolve_annual_da(_facts(us), years)
        self.assertEqual(r["status"], "consolidated")
        self.assertAlmostEqual(r["values"]["2021-05-31"], 744e6, places=0)
        self.assertAlmostEqual(r["values"]["2026-05-31"], 747e6, places=0)
        # overlap year uses the consolidated total, not a double-count
        self.assertAlmostEqual(r["values"]["2024-05-31"], 796e6, places=0)

    def test_partial_depreciation_window_is_derived(self):
        # GOOGL-like: Depreciation present for 5 of 6 years (missing the earliest), but the
        # trailing 3-year window is complete -> derived (not unavailable).
        years = ["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31",
                 "2024-12-31", "2025-12-31"]
        us = {
            "Depreciation": {"units": {"USD": [
                _fy(10.273e9, "2021-12-31"), _fy(13.475e9, "2022-12-31"),
                _fy(11.946e9, "2023-12-31"), _fy(15.311e9, "2024-12-31"),
                _fy(21.136e9, "2025-12-31")]}},
            "FinanceLeaseRightOfUseAssetAmortization": {"units": {"USD": [
                _fy(0.553e9, "2025-12-31")]}},
        }
        r = resolve_annual_da(_facts(us), years)
        self.assertEqual(r["status"], "derived")
        self.assertAlmostEqual(r["values"]["2025-12-31"], 21.136e9 + 0.553e9, places=0)

    def test_quarterly_amortization_annualized(self):
        # GOOGL-like: intangible amortization reported only as 3-month 10-Q increments.
        years = ["2024-12-31", "2025-12-31"]
        us = {
            "Depreciation": {"units": {"USD": [
                _fy(15.311e9, "2024-12-31"), _fy(21.136e9, "2025-12-31")]}},
            "AmortizationOfIntangibleAssets": {"units": {"USD": [
                {"start": "2025-01-01", "end": "2025-03-31", "form": "10-Q",
                 "filed": "2025-04-30", "val": 122e6},
                {"start": "2025-04-01", "end": "2025-06-30", "form": "10-Q",
                 "filed": "2025-07-23", "val": 124e6},
                {"start": "2025-07-01", "end": "2025-09-30", "form": "10-Q",
                 "filed": "2025-10-29", "val": 129e6},
            ]}},
        }
        r = resolve_annual_da(_facts(us), years)
        self.assertEqual(r["status"], "derived")
        # FY2025 D&A = depreciation + summed 3 quarters of amortization
        self.assertAlmostEqual(r["values"]["2025-12-31"], 21.136e9 + 375e6, places=0)


class TtmDaResolverTests(unittest.TestCase):
    def test_prefers_most_recent_tag(self):
        # Stale total tag (older period) + current total tag (newer period).
        us = {
            "DepreciationDepletionAndAmortization": {"units": {"USD": [
                _annual(10.678e9, "2019-01-31", filed="2019-03-15")]}},
            "DepreciationAmortizationAndAccretionNet": {"units": {"USD": [
                _annual(14.203e9, "2026-01-31", filed="2026-03-15")]}},
        }
        r = resolve_ttm_da(_facts(us))
        # must pick the newer tag, not the stale FY2019 value
        self.assertEqual(r["tag"], "DepreciationAmortizationAndAccretionNet")
        self.assertEqual(r["value"], 14.203e9)


if __name__ == "__main__":
    unittest.main()
