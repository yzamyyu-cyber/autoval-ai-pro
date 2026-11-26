import unittest
from autoval.ttm import trailing_twelve_months


def _dur(val, start, end, form="10-K", filed="2026-02-01"):
    return {"start": start, "end": end, "form": form, "filed": filed, "val": val}


def _facts(tag="Revenue", annual=1000.0, ytd_cur=None, ytd_prior=None):
    """Synthetic cumulative-YTD + annual facts (calendar fiscal year)."""
    us = {tag: {"units": {"USD": []}}}
    us[tag]["units"]["USD"].append(_dur(annual, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"))
    if ytd_prior is not None:
        us[tag]["units"]["USD"].append(_dur(ytd_prior, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"))
    if ytd_cur is not None:
        us[tag]["units"]["USD"].append(_dur(ytd_cur, "2026-01-01", "2026-09-30", "10-Q", "2026-10-30"))
    return {"facts": {"us-gaap": us}}


class TtmTests(unittest.TestCase):
    def test_ttm_formula(self):
        # FY2025=1000, YTD2026=800, YTD2025=700 -> TTM = 1000 + 800 - 700 = 1100
        r = trailing_twelve_months(_facts(ytd_cur=800.0, ytd_prior=700.0), ("Revenue",), today="2026-11-11")
        self.assertEqual(r["basis"], "ttm")
        self.assertAlmostEqual(r["value"], 1100.0)
        self.assertEqual(r["ytd_end"], "2026-09-30")

    def test_annual_fallback_when_no_newer_quarter(self):
        # no 10-Q YTD -> TTM == latest FY
        r = trailing_twelve_months(_facts(), ("Revenue",), today="2026-11-11")
        self.assertEqual(r["basis"], "annual")
        self.assertAlmostEqual(r["value"], 1000.0)
        self.assertIsNone(r["ytd_end"])

    def test_missing_prior_ytd_returns_none(self):
        # current YTD present but prior-year YTD missing -> cannot reconcile
        r = trailing_twelve_months(_facts(ytd_cur=800.0, ytd_prior=None), ("Revenue",), today="2026-11-11")
        self.assertIsNone(r)

    def test_single_quarter_not_treated_as_full_year(self):
        # a single-quarter fact (start != fiscal-year start) must be ignored as YTD
        f = _facts()
        f["facts"]["us-gaap"]["Revenue"]["units"]["USD"].append(
            _dur(250.0, "2026-07-01", "2026-09-30", "10-Q", "2026-10-30"))
        r = trailing_twelve_months(f, ("Revenue",), today="2026-11-11")
        self.assertEqual(r["basis"], "annual")  # single-quarter fact ignored; no YTD detected
        self.assertAlmostEqual(r["value"], 1000.0)

    def test_stale_ytd_before_fy_end_ignored(self):
        # a YTD fact ending before the latest FY end is not "newer" data
        f = _facts(ytd_cur=700.0, ytd_prior=500.0)
        # move the current YTD end to before FY end (2025-09-30 < 2025-12-31)
        f["facts"]["us-gaap"]["Revenue"]["units"]["USD"] = [
            _dur(1000.0, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
            _dur(700.0, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
        ]
        r = trailing_twelve_months(f, ("Revenue",), today="2026-11-11")
        self.assertEqual(r["basis"], "annual")

    def test_52_53_week_fiscal_calendar(self):
        # HD-style: fiscal-year start shifts by ~1 day each year (52/53-week calendar).
        us = {"Revenue": {"units": {"USD": [
            _dur(1000, "2025-02-03", "2026-02-01", "10-K", "2026-03-15"),
            _dur(700, "2025-02-03", "2025-11-02", "10-Q", "2025-12-10"),
            _dur(800, "2026-02-02", "2026-11-01", "10-Q", "2026-12-10"),
        ]}}}
        r = trailing_twelve_months({"facts": {"us-gaap": us}}, ("Revenue",), today="2026-12-11")
        self.assertEqual(r["basis"], "ttm")
        self.assertAlmostEqual(r["value"], 1000 + 800 - 700)

    def test_rolling_12_month_excluded(self):
        # AMZN-style OCF: a rolling 12-month (364d) 10-Q fact must not be treated as YTD.
        us = {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            _dur(1395, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
            _dur(850, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
            _dur(1138, "2026-01-01", "2026-09-30", "10-Q", "2026-10-30"),
            _dur(1683, "2025-10-01", "2026-09-30", "10-Q", "2026-10-30"),  # rolling 12m
        ]}}}
        r = trailing_twelve_months({"facts": {"us-gaap": us}},
                                   ("NetCashProvidedByUsedInOperatingActivities",),
                                   today="2026-11-11")
        self.assertEqual(r["basis"], "ttm")
        self.assertAlmostEqual(r["value"], 1395 + 1138 - 850)  # rolling 1683 excluded

    def test_future_filed_fact_excluded(self):
        # a YTD fact filed after the valuation date must not be selected (no look-ahead)
        us = {"Revenue": {"units": {"USD": [
            _dur(1000, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
            _dur(700, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
            _dur(800, "2026-01-01", "2026-09-30", "10-Q", "2027-01-15"),  # future filed
        ]}}}
        r = trailing_twelve_months({"facts": {"us-gaap": us}}, ("Revenue",), today="2026-11-11")
        self.assertEqual(r["basis"], "annual")  # future-filed YTD excluded -> annual fallback


if __name__ == "__main__":
    unittest.main()
