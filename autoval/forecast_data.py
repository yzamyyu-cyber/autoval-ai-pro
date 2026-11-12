"""SEC historical financial-data retrieval and normalization for the driver forecast.

Consolidated (not segment) data for U.S.-listed nonfinancial SEC filers. Missing
drivers are reported, never invented.
"""
from __future__ import annotations
from .sec import annual_values, latest_instant, instant_at_date, sec_lookup, fetch_json, FACTS_URL

_REVENUE_TAGS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues")
_PRETAX_TAGS = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
)
_DA_COMPONENT_TAGS = ("Depreciation", "AmortizationOfIntangibleAssets",
                      "FinanceLeaseRightOfUseAssetAmortization")


def _align(*series_dicts):
    """Intersect fiscal-year keys and return (sorted_years, [value_lists...])."""
    keys = set(series_dicts[0])
    for s in series_dicts[1:]:
        keys &= set(s)
    keys = sorted(keys)
    out = []
    for s in series_dicts:
        out.append([s[k]["value"] for k in keys])
    return keys, out


def _operating_nwc_series(facts, fiscal_years) -> list:
    """Annual operating NWC at each fiscal year-end (operating current assets minus
    operating current liabilities). Returns a list aligned to `fiscal_years`; a year is
    None where the balance-sheet facts are unavailable. Excludes cash, investments,
    interest-bearing debt and financing liabilities."""
    def val_at(tag, asof):
        v = instant_at_date(facts, "us-gaap", tag, asof)
        return v["value"] if v else None

    series = []
    for asof in fiscal_years:
        ar = val_at("AccountsReceivableNetCurrent", asof)
        inv = val_at("InventoryNet", asof)
        ap = val_at("AccountsPayableCurrent", asof)
        ccl = val_at("ContractWithCustomerLiabilityCurrent", asof)
        acc = val_at("AccruedLiabilitiesCurrent", asof)
        if ar is None and inv is None and ap is None and ccl is None and acc is None:
            series.append(None)
            continue
        assets = (ar or 0.0) + (inv or 0.0)
        liabilities = (ap or 0.0) + (ccl or 0.0) + (acc or 0.0)
        series.append(assets - liabilities)
    return series


def retrieve_history(ticker: str, user_agent: str) -> dict:
    cik, name = sec_lookup(ticker, user_agent)
    facts = fetch_json(FACTS_URL.format(cik=cik), user_agent)

    revenue = annual_values(facts, _REVENUE_TAGS)
    opinc = annual_values(facts, ("OperatingIncomeLoss",))
    capex = annual_values(facts, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"))
    taxes = annual_values(facts, ("IncomeTaxExpenseBenefit",))
    pretax = annual_values(facts, _PRETAX_TAGS)

    years, (rev_v, op_v, cx_v) = _align(revenue, opinc, capex)
    if len(years) > 6:
        years = years[-6:]
        rev_v = rev_v[-6:]
        op_v = op_v[-6:]
        cx_v = cx_v[-6:]
    if len(years) < 2:
        raise ValueError(
            f"Insufficient annual financial history for {ticker} ({len(years)} matched years); "
            f"driver forecast requires at least 2 years of revenue/operating income/capex.")

    # D&A: sum distinct, non-overlapping components; fall back to the total tag.
    da_tot = {y: 0.0 for y in years}
    da_detail = []
    used = 0
    for tag in _DA_COMPONENT_TAGS:
        series = annual_values(facts, (tag,))
        vals = {y: series[y]["value"] for y in years if y in series}
        if vals:
            used += 1
            da_detail.append({"tag": tag, "years_present": sorted(vals)})
            for y, v in vals.items():
                da_tot[y] += v
    if used == 0:
        total = annual_values(facts, ("DepreciationDepletionAndAmortization",))
        vals = {y: total[y]["value"] for y in years if y in total}
        if vals:
            da_detail.append({"tag": "DepreciationDepletionAndAmortization", "years_present": sorted(vals)})
            for y, v in vals.items():
                da_tot[y] += v
    da_v = [da_tot[y] for y in years]

    # observed effective tax (reference only, NOT reused as normalized operating tax)
    tax_v = []
    for y in years:
        if y in taxes and y in pretax and pretax[y]["value"] > 0:
            t = taxes[y]["value"] / pretax[y]["value"]
            tax_v.append(t if 0 <= t <= 0.5 else None)
        else:
            tax_v.append(None)

    nwc_series = _operating_nwc_series(facts, years)
    nwc_present = [v for v in nwc_series if v is not None]

    limitations = []
    warnings = []
    if used == 0:
        warnings.append("No D&A component tags found; D&A total unavailable.")
    if not nwc_present:
        limitations.append("Operating NWC facts unavailable; NWC ratio treated as zero (disclosed).")
    elif any(v is None for v in nwc_series):
        limitations.append("Some fiscal-year NWC observations are missing; only available years used.")
    if len(years) < 6:
        limitations.append(f"Only {len(years)} fiscal years of history (sample-size limitation).")

    return {
        "ticker": ticker, "company": name, "cik": cik,
        "fiscal_years": years,
        "revenue": rev_v, "operating_income": op_v, "capex": cx_v,
        "da": da_v, "da_detail": da_detail,
        "effective_tax_rate": tax_v,
        "nwc": nwc_series,
        "nwc_latest": nwc_present[-1] if nwc_present else None,
        "asof": years[-1],
        "units": "USD",
        "limitations": limitations,
        "warnings": warnings,
    }
