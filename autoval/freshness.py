"""Financial-data freshness detection (reusable).

Compares the latest periodic filing (10-K / 10-Q) reporting period against newer
8-K Item 2.02 "Results of Operations" earnings releases, using the *reporting period*
(`reportDate`), not merely the filing date. Returns an explicit state:
  - up-to-date               no newer results than the latest periodic filing
  - newer-results-available  an 8-K earnings release covers a later period
  - unknown                  the check could not be completed (provider/network)
  - offline / saved-data     no live check was attempted (caller supplies cached data)

The valuation must retain the latest complete periodic-filing basis and only surface a
"newer results available" notice — it must not switch to an earnings-release basis unless
every essential input has been reconciled (no look-ahead bias).
"""
from __future__ import annotations
from urllib.request import Request, urlopen
import json

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def fetch_submissions(cik: int, user_agent: str) -> dict:
    req = Request(SUBMISSIONS.format(cik=cik), headers={"User-Agent": user_agent})
    return json.load(urlopen(req, timeout=30))


def check_freshness(cik: int, user_agent: str) -> dict:
    """Return freshness state and periods. Never raises — unavailable => status 'unknown'."""
    base = {"status": "unknown", "latest_periodic_filing": None,
            "latest_periodic_report_date": None, "newer_earnings_release": None,
            "newer_earnings_report_date": None, "latest_filing": None}
    try:
        subs = fetch_submissions(cik, user_agent)
    except Exception:
        return base

    rec = subs.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    dates = rec.get("filingDate", [])
    report_dates = rec.get("reportDate", [""] * len(forms))
    items = rec.get("items", [""] * len(forms))

    latest_periodic_filing = None
    latest_periodic_report = None
    newer_earnings_filing = None
    newer_earnings_report = None
    latest_filing = None

    for form, d, rd, item in zip(forms, dates, report_dates, items):
        if d and (latest_filing is None or d > latest_filing):
            latest_filing = d
        if form in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
            if latest_periodic_filing is None or d > latest_periodic_filing:
                latest_periodic_filing = d
                latest_periodic_report = rd
        # 8-K Item 2.02 = earnings release
        if form == "8-K" and "2.02" in (item or ""):
            if newer_earnings_filing is None or d > newer_earnings_filing:
                newer_earnings_filing = d
                newer_earnings_report = rd

    base.update(latest_periodic_filing=latest_periodic_filing,
                latest_periodic_report_date=latest_periodic_report,
                newer_earnings_release=newer_earnings_filing,
                newer_earnings_report_date=newer_earnings_report,
                latest_filing=latest_filing)

    # "newer results" when the earnings release covers a LATER reporting period than the
    # latest periodic filing (compare reportDate first; fall back to filingDate). When an
    # 8-K is newer by filing date but its reportDate is unavailable, the period is
    # unconfirmed — never present reportDate as a confirmed quarter-end.
    newer = False
    if newer_earnings_report and latest_periodic_report:
        newer = newer_earnings_report > latest_periodic_report
    elif newer_earnings_filing and latest_periodic_filing:
        newer = newer_earnings_filing > latest_periodic_filing
    if newer and not newer_earnings_report:
        base["status"] = "newer-disclosure-period-unconfirmed"
    elif newer:
        base["status"] = "newer-results-available"
    else:
        base["status"] = "up-to-date"
    return base
