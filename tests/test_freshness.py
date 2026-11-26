import unittest
from unittest.mock import patch
from autoval.freshness import check_freshness


class FreshnessTests(unittest.TestCase):
    def _subs(self, forms, dates, docs, items=None, report_dates=None):
        n = len(forms)
        return {"filings": {"recent": {
            "form": forms, "filingDate": dates, "primaryDocument": docs,
            "accessionNumber": ["a" * 18] * n,
            "items": items if items is not None else [""] * n,
            "reportDate": report_dates if report_dates is not None else [""] * n,
        }}}

    def test_fresh_when_no_newer_earnings(self):
        subs = self._subs(
            ["10-K", "10-Q", "8-K"], ["2026-02-01", "2026-05-01", "2026-06-01"],
            ["a10k.htm", "a10q.htm", "a8k.htm"], ["", "", "5.02,9.01"])
        with patch("autoval.freshness.fetch_submissions", return_value=subs):
            r = check_freshness(1, "x@y.com")
        self.assertEqual(r["status"], "up-to-date")

    def test_stale_when_earnings_release_newer_than_10q(self):
        subs = self._subs(
            ["10-K", "10-Q", "8-K"], ["2026-02-01", "2026-05-01", "2026-11-17"],
            ["a10k.htm", "a10q.htm", "nvda-20261117.htm"], ["", "", "2.02,9.01"],
            ["2025-12-31", "2026-07-26", "2026-10-25"])
        with patch("autoval.freshness.fetch_submissions", return_value=subs):
            r = check_freshness(1, "x@y.com")
        self.assertEqual(r["status"], "newer-results-available")
        self.assertEqual(r["newer_earnings_release"], "2026-11-17")

    def test_look_ahead_prevented(self):
        subs = self._subs(
            ["10-Q", "8-K"], ["2026-07-26", "2026-11-17"],
            ["nvda10q.htm", "ex991.htm"], ["", "2.02,9.01"],
            ["2026-07-26", "2026-10-25"])
        with patch("autoval.freshness.fetch_submissions", return_value=subs):
            r = check_freshness(1, "x@y.com")
        self.assertEqual(r["status"], "newer-results-available")

    def test_unconfirmed_period_when_report_date_missing(self):
        subs = self._subs(
            ["10-Q", "8-K"], ["2026-07-26", "2026-11-17"],
            ["nvda10q.htm", "ex991.htm"], ["", "2.02,9.01"],
            ["2026-07-26", ""])  # 8-K reportDate absent -> period unconfirmed
        with patch("autoval.freshness.fetch_submissions", return_value=subs):
            r = check_freshness(1, "x@y.com")
        self.assertEqual(r["status"], "newer-disclosure-period-unconfirmed")


if __name__ == "__main__":
    unittest.main()
