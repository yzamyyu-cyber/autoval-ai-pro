#!/usr/bin/env python3
"""Independent SEC source-data reconciliation (additive TTM methodology).

For each additive metric, independently reconstructs:
    TTM = latest completed FY + current-year YTD - prior-year-comparable YTD
and compares each component AND the reconstructed TTM against AutoVal's TTM value
(read from the sanitized fixture). Records filing accession, XBRL tag, period start/end,
filing date and units. Does NOT import autoval and does NOT reuse a prior companyfacts
snapshot for two calculations - it re-reads the filing metadata directly.

Usage: .venv/bin/python evidence/reconcile_source.py
"""
from __future__ import annotations
import csv
import json
import os
from collections import Counter
from datetime import date
from urllib.request import Request, urlopen

FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
INDEX = "https://www.sec.gov/files/company_tickers.json"
UA = "AutoValStudentResearch your-school-email@example.edu"

TICKERS = ("MSFT", "AMZN", "AAPL", "HD", "GOOGL", "TSLA", "NVDA")
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tests", "fixtures")

METRICS = [
    ("revenue", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"), "USD", "revenue"),
    ("operating_income", ("OperatingIncomeLoss",), "USD", "operating_income"),
    ("operating_cash_flow", ("NetCashProvidedByUsedInOperatingActivities",), "USD", "operating_cash_flow"),
    ("capex_gross_cash", ("PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipment"), "USD", "capex"),
    ("dna", ("DepreciationDepletionAndAmortization",), "USD", None),
    ("finance_lease_additions", ("RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability",), "USD", None),
]


def _resolve_tag(facts, tags, unit, today):
    """Pick the tag that has the latest annual fact (handles tag migration)."""
    best_tag, best_end = None, ""
    for tag in tags:
        for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get(unit, []):
            if it.get("form") not in ("10-K", "10-K/A"):
                continue
            if not it.get("end") or not it.get("filed") or it["filed"] > today:
                continue
            if it["end"] > best_end:
                best_end, best_tag = it["end"], tag
    return best_tag or tags[0]


def get(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urlopen(req, timeout=30))


def cik_of(ticker):
    for e in get(INDEX).values():
        if str(e["ticker"]).upper() == ticker.upper():
            return int(e["cik_str"])
    raise ValueError(f"no CIK for {ticker}")


def _annual(facts, tag, unit, today):
    out = {}
    for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get(unit, []):
        if it.get("form") not in ("10-K", "10-K/A"):
            continue
        if not it.get("start") or not it.get("end") or not it.get("filed") or it["filed"] > today:
            continue
        try:
            days = (date.fromisoformat(it["end"]) - date.fromisoformat(it["start"])).days
        except ValueError:
            continue
        if not 330 <= days <= 390:
            continue
        k = it["end"]
        if k not in out or it["filed"] > out[k]["filed"]:
            out[k] = dict(it); out[k]["value"] = float(it["val"])
    return out


def _cumulative_ytd(facts, tag, unit, today, fy_start_md):
    out = []
    for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get(unit, []):
        if it.get("form") not in ("10-Q", "10-Q/A"):
            continue
        if not it.get("start") or not it.get("end") or not it.get("filed") or it["filed"] > today:
            continue
        try:
            s = date.fromisoformat(it["start"]); e = date.fromisoformat(it["end"])
        except ValueError:
            continue
        days = (e - s).days
        cum = 100 < days < 360
        if not cum and 75 <= days <= 100:
            cum = abs((date(2000, s.month, s.day) - fy_start_md).days) <= 6
        if cum:
            out.append({"value": float(it["val"]), "end": it["end"], "start": it["start"],
                        "days": days, "accn": it.get("accn", ""), "filed": it.get("filed", "")})
    return out


def ttm(annual, ytds):
    if not annual:
        return None
    fy_end = max(annual); fy = annual[fy_end]["value"]
    if not ytds:
        return {"value": fy, "fy_end": fy_end, "ytd_end": None, "basis": "annual"}
    cur = max(ytds, key=lambda x: x["end"])
    if cur["end"] <= fy_end:
        return {"value": fy, "fy_end": fy_end, "ytd_end": None, "basis": "annual"}
    cur_start = date.fromisoformat(cur["start"])
    prior = None
    for y in ytds:
        if y is cur:
            continue
        if date.fromisoformat(y["end"]) >= cur_start:
            continue
        if abs(y["days"] - cur["days"]) > 15:
            continue
        if prior is None or y["end"] > prior["end"]:
            prior = y
    if prior is None:
        return None
    return {"value": fy + cur["value"] - prior["value"], "fy_end": fy_end,
            "ytd_end": cur["end"], "basis": "ttm", "fy": fy, "cur": cur, "prior": prior}


def main():
    today = date.today().isoformat()
    header = ["ticker", "metric", "accession", "xbrl_tag", "period_start", "period_end",
              "filing_date", "units", "reported_fy", "reported_current_ytd",
              "reported_prior_ytd", "derived_ttm", "autoval_ttm", "difference", "status"]
    rows = [header]

    for t in TICKERS:
        cik = cik_of(t)
        facts = get(FACTS.format(cik=cik))
        fx = json.load(open(os.path.join(FIXTURES, f"{t}.json")))
        autoval_ttm = (fx.get("history") or {}).get("ttm") or {}

        for label, tags, unit, key in METRICS:
            tag = _resolve_tag(facts, tags, unit, today)
            annual = _annual(facts, tag, unit, today)
            if not annual:
                rows.append([t, label, "", tag, "", "", "", unit, "", "", "", "", "", "", "UNAVAILABLE"])
                continue
            fy_start = date.fromisoformat(annual[max(annual)]["start"])
            fy_start_md = date(2000, fy_start.month, fy_start.day)
            ytds = _cumulative_ytd(facts, tag, unit, today, fy_start_md)
            r = ttm(annual, ytds)

            autoval = autoval_ttm.get(key) if key else None
            derived = r["value"] if r else None
            if autoval is None:
                status = "DERIVED" if derived is not None else "UNAVAILABLE"
                rows.append([t, label, (r.get("cur", {}) or {}).get("accn", ""), tag,
                             (r.get("cur", {}) or {}).get("start", ""), r.get("ytd_end", ""),
                             (r.get("cur", {}) or {}).get("filed", ""), unit,
                             (r.get("fy") if r else ""), ((r.get("cur") or {}).get("value", "") if r else ""),
                             ((r.get("prior") or {}).get("value", "") if r else ""), derived, "", "", status])
                continue
            diff = (derived - autoval) if (derived is not None and autoval is not None) else ""
            status = "PASS" if (diff != "" and abs(diff) < 0.5e6) else ("MISMATCH" if diff != "" else "UNAVAILABLE")
            rows.append([t, label, (r.get("cur", {}) or {}).get("accn", ""), tag,
                         (r.get("cur", {}) or {}).get("start", ""), r.get("ytd_end", ""),
                         (r.get("cur", {}) or {}).get("filed", ""), unit,
                         (r.get("fy") if r else ""), ((r.get("cur") or {}).get("value", "") if r else ""),
                         ((r.get("prior") or {}).get("value", "") if r else ""), derived, autoval, diff, status])

    with open("evidence/financial_reconciliation.csv", "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    c = Counter(r[14] for r in rows[1:])
    print("reconciliation summary:", dict(c))
    print("PASS rows:", sum(1 for r in rows[1:] if r[14] == "PASS"))
    print("MISMATCH rows:", sum(1 for r in rows[1:] if r[14] == "MISMATCH"))


if __name__ == "__main__":
    main()
