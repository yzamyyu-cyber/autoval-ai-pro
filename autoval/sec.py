"""SEC EDGAR XBRL extraction (U.S. nonfinancial issuers, US GAAP).

Real SEC data require reviewing definitions/units/filing periods. No silent
imputation of missing core FCFF components.
"""
from __future__ import annotations
from datetime import date
from urllib.parse import quote
import os
import requests
from .finance import fcff_from_us_gaap_cashflows

INDEX_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def fetch_json(url: str, user_agent: str) -> dict:
    if not user_agent or "@" not in user_agent:
        raise ValueError("Set SEC_USER_AGENT to a descriptive app name + real contact email, e.g. StudentProject your_email@example.edu")
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    return response.json()


def sec_lookup(ticker: str, user_agent: str) -> tuple[int, str]:
    index = fetch_json(INDEX_URL, user_agent)
    entries = index.values() if isinstance(index, dict) else index
    for item in entries:
        if str(item["ticker"]).upper() == ticker.upper():
            return int(item["cik_str"]), item["title"]
    raise ValueError(f"No exact SEC CIK match for {ticker}; only U.S.-listed SEC filers are supported")


def concept(facts: dict, taxonomy: str, tag: str, unit: str = "USD") -> list[dict]:
    return facts.get("facts", {}).get(taxonomy, {}).get(tag, {}).get("units", {}).get(unit, [])


def annual_values(facts: dict, tags: tuple[str, ...], today: str | None = None,
                  unit: str = "USD") -> dict:
    """Use ~1-year 10-K duration facts and the freshest filing of each fiscal-end period.

    When several candidate tags are supplied, earlier tags take priority for a given
    fiscal year, and later tags fill only the fiscal years the earlier tags do not
    report. This supports issuers that migrate an element between XBRL tags over time
    (e.g. InterestExpense -> InterestExpenseNonoperating) without silently dropping the
    years reported under either tag.
    """
    today = today or date.today().isoformat()
    merged: dict = {}
    for tag in tags:
        raw = concept(facts, "us-gaap", tag, unit)
        by_year: dict = {}
        for entry in raw:
            if entry.get("form") not in ("10-K", "10-K/A") or not entry.get("start") or not entry.get("end"):
                continue
            if not entry.get("filed") or entry["filed"] > today:
                continue
            try:
                days = (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days
            except (TypeError, ValueError):
                continue
            if days < 330 or days > 390:
                continue
            key = entry["end"]
            if key not in by_year or entry["filed"] > by_year[key]["filed"]:
                by_year[key] = {"value": float(entry["val"]), "end": key,
                                "start": entry["start"], "filed": entry["filed"],
                                "tag": tag, "form": entry["form"]}
        for key, fact in by_year.items():
            if key not in merged:
                merged[key] = fact
    return merged


def latest_instant(facts: dict, taxonomy: str, tags: tuple[str, ...],
                   unit: str = "USD", today: str | None = None) -> dict | None:
    today = today or date.today().isoformat()
    for tag in tags:
        candidates = [item for item in concept(facts, taxonomy, tag, unit)
                      if not item.get("start") and item.get("end") and item.get("filed")
                      and item["filed"] <= today
                      and item.get("form") in ("10-K", "10-K/A", "10-Q", "10-Q/A")]
        if candidates:
            winner = max(candidates, key=lambda x: (x["end"], x["filed"]))
            return {"value": float(winner["val"]), "end": winner["end"],
                    "filed": winner["filed"], "form": winner["form"], "tag": tag}
    return None


def instant_at_date(facts: dict, taxonomy: str, tag: str, asof: str,
                    unit: str = "USD") -> dict | None:
    """Return the freshest point-in-time fact for `tag` reported exactly at `asof`,
    or None when no fact exists at that reporting date.

    Stale facts (other reporting dates) are intentionally excluded so that a
    current-period reconciliation never silently mixes balance-sheet dates.
    """
    candidates = [item for item in concept(facts, taxonomy, tag, unit)
                  if not item.get("start") and item.get("end") == asof
                  and item.get("filed")
                  and item.get("form") in ("10-K", "10-K/A", "10-Q", "10-Q/A")]
    if not candidates:
        return None
    winner = max(candidates, key=lambda x: x["filed"])
    return {"value": float(winner["val"]), "end": winner["end"],
            "filed": winner["filed"], "form": winner["form"], "tag": tag}


def instant_at_date_multi(facts: dict, taxonomy: str, tags: tuple, asof: str,
                          unit: str = "USD") -> dict | None:
    """First tag (priority order) with a point-in-time fact at `asof`; else None."""
    for tag in tags:
        v = instant_at_date(facts, taxonomy, tag, asof, unit)
        if v is not None:
            return v
    return None


def quarterly_values(facts: dict, tags: tuple[str, ...], today: str | None = None,
                     unit: str = "USD") -> dict:
    """~3-month 10-Q duration facts keyed by quarter-end date (freshest filing per quarter).

    Earlier tags take priority for a given quarter, later tags fill gaps (same
    convention as `annual_values`)."""
    today = today or date.today().isoformat()
    merged: dict = {}
    for tag in tags:
        raw = concept(facts, "us-gaap", tag, unit)
        by_q: dict = {}
        for entry in raw:
            if entry.get("form") not in ("10-Q", "10-Q/A") or not entry.get("start") or not entry.get("end"):
                continue
            if not entry.get("filed") or entry["filed"] > today:
                continue
            try:
                days = (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days
            except (TypeError, ValueError):
                continue
            if days < 70 or days > 100:
                continue
            key = entry["end"]
            if key not in by_q or entry["filed"] > by_q[key]["filed"]:
                by_q[key] = {"value": float(entry["val"]), "end": key,
                             "start": entry["start"], "filed": entry["filed"],
                             "tag": tag, "form": entry["form"]}
        for key, fact in by_q.items():
            if key not in merged:
                merged[key] = fact
    return merged


def get_sec_financials(ticker: str, user_agent: str) -> dict:
    cik, name = sec_lookup(ticker, user_agent)
    url = FACTS_URL.format(cik=cik)
    facts = fetch_json(url, user_agent)
    cfo = annual_values(facts, ("NetCashProvidedByUsedInOperatingActivities",))
    capex = annual_values(facts, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"))
    interest = annual_values(facts, ("InterestExpenseNonoperating", "InterestExpense"))
    cash_interest = annual_values(facts, ("InterestPaidNet", "InterestPaid"))
    taxes = annual_values(facts, ("IncomeTaxExpenseBenefit",))
    pretax = annual_values(facts, (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ))
    common = sorted(set(cfo) & set(capex) & set(interest))
    if len(common) < 2:
        missing = [k for k,v in (("operating cash flow",cfo),("capital expenditure",capex),
                                  ("interest expense",interest)) if not v]
        raise ValueError(
            f"Insufficient matched annual SEC facts for reliable FCFF (matched years={len(common)}; "
            f"missing categories={missing}). Stop; inspect financial statements manually or use another ticker."
        )
    common = common[-4:]
    hist = []
    records = []
    for end in common:
        tr = 0.21
        tax_note = "21% explicit policy fallback; effective tax data missing/out of range"
        if end in taxes and end in pretax and pretax[end]["value"] > 0:
            observed = taxes[end]["value"] / pretax[end]["value"]
            if 0 <= observed <= 0.5:
                tr = observed
                tax_note = f"SEC observed tax expense / pretax income ({tr:.1%})"
        int_addback = cash_interest[end]["value"] if end in cash_interest else interest[end]["value"]
        int_addback_note = ("cash interest paid" if end in cash_interest
                            else "interest expense (proxy; cash interest paid unavailable)")
        cf = fcff_from_us_gaap_cashflows(cfo[end]["value"], capex[end]["value"], int_addback, tr)
        hist.append({"year_end": end, "fcff_usd": cf})
        records.append({"year_end": end, "cfo": cfo[end], "capex": capex[end],
                        "interest": interest[end], "cash_interest": cash_interest.get(end),
                        "interest_addback": int_addback, "interest_addback_note": int_addback_note,
                        "tax": taxes.get(end),
                        "pretax": pretax.get(end), "tax_rate": tr, "tax_rate_note": tax_note,
                        "derived_fcff_usd": cf})
    shares = latest_instant(facts, "dei", ("EntityCommonStockSharesOutstanding",), "shares")
    if shares is None:
        # Weighted-average annual diluted shares are not interchangeable with point-in-time shares.
        raise ValueError("Latest point-in-time outstanding shares unavailable; do not silently substitute weighted-average diluted shares")
    cash = latest_instant(facts, "us-gaap", ("CashAndCashEquivalentsAtCarryingValue",))
    if cash is None:
        raise ValueError("Missing cash SEC facts; cannot calculate net debt safely")
    asof = cash["end"]

    long_debt = instant_at_date_multi(facts, "us-gaap",
        ("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"), asof)
    if long_debt is None:
        raise ValueError(
            f"Noncurrent long-term debt not reported at cash reporting date {asof}; manual reconciliation required")

    # Current-period debt components must be reported at the same date as cash.
    # Stale facts (other dates) are excluded and disclosed, never guessed as a current zero.
    assumptions = []
    excluded = []

    def debt_component(label: str, tags: tuple):
        for tag in tags:
            at_date = instant_at_date(facts, "us-gaap", tag, asof)
            if at_date is not None:
                return at_date, at_date["value"]
        latest = latest_instant(facts, "us-gaap", tags)
        if latest is None:
            assumptions.append(f"{label} ({', '.join(tags)}) not reported with supported tags; counted as zero (possible understatement)")
            excluded.append({"tag": tags[0], "status": "absent", "value_used": 0.0})
            return None, 0.0
        if abs(latest["value"]) < 0.5:
            assumptions.append(
                f"{label} ({latest['tag']}) stale: last reported {latest['end']} = 0; excluded from current period {asof} "
                f"and counted as zero (not verified current; possible understatement)")
            excluded.append({"tag": latest["tag"], "status": "stale_zero", "last_end": latest["end"],
                             "last_value": latest["value"], "value_used": 0.0})
            return None, 0.0
        raise ValueError(
            f"{label} ({latest['tag']}) last reported {latest['end']} with nonzero value {latest['value']:,.0f} "
            f"but not at current reporting date {asof}; cannot reconcile safely — manual review required")

    short_debt, short_val = debt_component("Short-term borrowings", ("ShortTermBorrowings", "CommercialPaper"))
    current_debt, current_val = debt_component("Current portion of long-term debt", ("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"))

    net_debt = long_debt["value"] + short_val + current_val - cash["value"]
    total_debt = long_debt["value"] + short_val + current_val

    # Nonoperating investments for the enterprise-to-equity bridge. Eligible securities
    # are reported as a range because the restricted portion within short-term
    # investments is usually only in the filing note, not a standalone XBRL fact.
    inv_assumptions = []
    inv_excluded = []

    def optional_investment(label: str, tag: str):
        at_date = instant_at_date(facts, "us-gaap", tag, asof)
        if at_date is not None:
            return at_date
        latest = latest_instant(facts, "us-gaap", (tag,))
        if latest is None:
            inv_assumptions.append(f"{label} ({tag}) not reported with supported tags; treated as zero")
            inv_excluded.append({"tag": tag, "status": "absent", "value_used": 0.0})
            return None
        inv_assumptions.append(
            f"{label} ({tag}) stale: last reported {latest['end']}; excluded and treated as zero at {asof}")
        inv_excluded.append({"tag": tag, "status": "stale", "last_end": latest["end"],
                             "last_value": latest["value"], "value_used": 0.0})
        return None

    st_inv = optional_investment("Short-term investments", "ShortTermInvestments")
    rest_inv = optional_investment("Restricted investments", "RestrictedInvestments")
    lt_inv = optional_investment("Long-term investments", "LongTermInvestments")
    short_term_investments = st_inv["value"] if st_inv else None
    restricted_investments = rest_inv["value"] if rest_inv else None
    long_term_investments = lt_inv["value"] if lt_inv else None

    latest_end = common[-1]
    income = annual_values(facts, ("NetIncomeLoss", "ProfitLoss")).get(latest_end)
    operating = annual_values(facts, ("OperatingIncomeLoss",)).get(latest_end)
    depreciation = annual_values(facts, (
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    )).get(latest_end)
    diluted = annual_values(facts, ("WeightedAverageNumberOfDilutedSharesOutstanding",), unit="shares")
    diluted_shares = diluted[latest_end]["value"] if latest_end in diluted else None
    return {
        "ticker": ticker.upper(), "company": name,
        "shares": shares["value"], "net_debt": net_debt,
        "diluted_shares": diluted_shares,
        "total_debt": total_debt,
        "cash_and_equivalents": cash["value"],
        "short_term_investments": short_term_investments,
        "restricted_investments": restricted_investments,
        "long_term_investments": long_term_investments,
        "restricted_in_short_term": None,
        "fcff_history": hist, "financial_asof": latest_end,
        "balance_sheet_asof": cash["end"], "share_count_asof": shares["end"],
        "ebit": operating["value"] if operating else None,
        "depreciation": depreciation["value"] if depreciation else None,
        "net_income": income["value"] if income else None,
        "source": {"provider": "SEC EDGAR XBRL companyfacts", "cik": cik, "url": url,
                   "units": "USD (except shares)", "annual_records": records,
                   "shares": shares, "cash": cash, "long_debt": long_debt,
                   "short_debt": short_debt, "current_debt": current_debt,
                   "excluded_debt_tags": excluded,
                   "debt_reconciliation": {
                       "reference_date": asof,
                       "long_term_debt": long_debt["value"],
                       "current_portion_long_term_debt": current_val,
                       "short_term_borrowings": short_val,
                       "total_debt": long_debt["value"] + current_val + short_val,
                       "cash_and_equivalents": cash["value"],
                       "net_debt": net_debt,
                   },
                   "investment_facts": {
                       "short_term_investments": st_inv,
                       "restricted_investments": rest_inv,
                       "long_term_investments": lt_inv,
                   },
                   "excluded_investment_tags": inv_excluded,
                   "investment_assumptions": inv_assumptions,
                   "disclosure_warnings": assumptions,
                   "method_note": "US-GAAP approximate FCFF = operating cash flow - capex + after-tax interest expense; needs filing-level review"},
    }
