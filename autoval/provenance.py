"""Structured financial provenance (reusable).

Every material financial input is represented by an evidence record that links it to its
original source, distinguishes *reported facts* from *derived calculations* from
*estimated assumptions*, and records verification status. Verification is two-tier:

  - `companyfacts`   — the extracted value agrees with the SEC companyfacts snapshot.
  - `independent`    — the value was checked against the original filing HTML / note
                       (only set when that independent inspection has actually happened).

This module never auto-promotes a companyfacts agreement to "independent" verification.
"""
from __future__ import annotations

KINDS = ("reported", "derived", "estimated", "user")


def record(record_id: str, company: str, snapshot_id: str, metric: str,
           source_url: str, accession: str, note: str, xbrl_tag: str, context: str,
           period_start: str, period_end: str, filed: str, units: str,
           reported_value, derived_value, formula: str, production_value,
           status: str, explanation: str, kind: str, dependencies=()):
    return {
        "evidence_id": record_id, "company": company, "snapshot_id": snapshot_id,
        "metric": metric, "source_url": source_url, "accession": accession,
        "statement_note": note, "xbrl_tag": xbrl_tag, "context": context,
        "period_start": period_start, "period_end": period_end, "filing_date": filed,
        "units": units, "reported_value": reported_value, "derived_value": derived_value,
        "formula": formula, "production_value": production_value,
        "verification_status": status, "explanation": explanation, "kind": kind,
        "dependencies": list(dependencies),
    }


def build_provenance(result: dict) -> list[dict]:
    """Build structured evidence records for a completed analysis result."""
    a = result.get("analysis") or {}
    fin = (result.get("provenance") or {}).get("financials") or {}
    snapshot_id = result.get("run_utc") or "unknown"
    company = result.get("ticker", "?")
    url = fin.get("url", "")
    acc = str(fin.get("cik", ""))
    units = fin.get("units", "USD")
    out = []

    # ---- reported facts (balance-sheet / share facts) ----
    for key, metric, note in (
        ("shares", "shares_outstanding", "Balance sheet / cover page"),
        ("cash", "cash_and_equivalents", "Balance sheet"),
        ("long_debt", "long_term_debt", "Balance sheet"),
        ("short_debt", "short_term_borrowings", "Balance sheet"),
        ("current_debt", "current_portion_long_term_debt", "Balance sheet"),
        ("finance_lease", "finance_lease_liability", "Balance sheet"),
    ):
        fact = fin.get(key)
        if fact:
            out.append(record(
                record_id=f"{company}.{metric}", company=company, snapshot_id=snapshot_id,
                metric=metric, source_url=url, accession=acc, note=note,
                xbrl_tag=fact.get("tag", ""), context="", period_start="",
                period_end=fact.get("end", ""), filed=fact.get("filed", ""), units=units,
                reported_value=fact.get("value"), derived_value=None, formula=None,
                production_value=fact.get("value"), status="companyfacts",
                explanation="Reported point-in-time fact; extracted value matches companyfacts.",
                kind="reported"))

    # ---- derived: net debt ----
    rec = fin.get("debt_reconciliation") or {}
    if rec:
        out.append(record(
            record_id=f"{company}.net_debt", company=company, snapshot_id=snapshot_id,
            metric="net_debt", source_url=url, accession=acc, note="Debt reconciliation",
            xbrl_tag="", context="", period_start="", period_end=rec.get("reference_date", ""),
            filed="", units=units, reported_value=None, derived_value=rec.get("net_debt"),
            formula="total_debt - cash_and_equivalents",
            production_value=rec.get("net_debt"), status="derived",
            explanation="Derived: total debt (incl. finance leases) less cash.",
            kind="derived", dependencies=[f"{company}.long_term_debt",
                                          f"{company}.current_portion_long_term_debt",
                                          f"{company}.short_term_borrowings",
                                          f"{company}.finance_lease_liability",
                                          f"{company}.cash_and_equivalents"]))

    # ---- derived: TTM revenue ----
    ttm = a.get("ttm") or {}
    if ttm.get("revenue") is not None:
        out.append(record(
            record_id=f"{company}.revenue_ttm", company=company, snapshot_id=snapshot_id,
            metric="revenue_ttm", source_url=url, accession=acc, note="Income statement (TTM)",
            xbrl_tag="", context="", period_start="", period_end=ttm.get("asof", ""),
            filed="", units=units, reported_value=None, derived_value=ttm.get("revenue"),
            formula="TTM = latest FY + current YTD - prior-year YTD",
            production_value=ttm.get("revenue"), status="derived",
            explanation="Derived TTM revenue (additive).", kind="derived"))

    # ---- estimated: drivers ----
    drivers = (((a.get("forecast") or {}).get("base") or {}).get("drivers") or {})
    for key, metric in (("revenue_growth", "revenue_growth"),
                        ("operating_margin", "operating_margin"),
                        ("capex_ratio", "capex_ratio"), ("da_ratio", "da_ratio"),
                        ("nwc_ratio", "nwc_ratio"), ("normalized_tax_rate", "tax_rate")):
        if key in drivers:
            out.append(record(
                record_id=f"{company}.{metric}", company=company, snapshot_id=snapshot_id,
                metric=metric, source_url=url, accession=acc, note="Forecast driver",
                xbrl_tag="", context="", period_start="", period_end="", filed="", units="",
                reported_value=None, derived_value=drivers[key], formula="trailing-3-year ratio",
                production_value=drivers[key], status="estimated",
                explanation="Estimated forecast driver (rule-based, not a reported fact).",
                kind="estimated"))

    return out
