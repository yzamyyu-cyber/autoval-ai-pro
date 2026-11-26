"""SEC historical financial-data retrieval and normalization for the driver forecast.

Consolidated (not segment) data for U.S.-listed nonfinancial SEC filers. Missing
drivers are reported, never invented.
"""
from __future__ import annotations
from .sec import annual_values, latest_instant, instant_at_date, sec_lookup, fetch_json, FACTS_URL
from .ttm import trailing_twelve_months

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
    if not opinc:
        # Some issuers (e.g. NKE) do not present a separate operating-income subtotal.
        # Reconstruct operating income = gross profit − selling, general & administrative
        # expense when both components are available and aligned (derived, disclosed).
        gross = annual_values(facts, ("GrossProfit",))
        sga = annual_values(facts, ("SellingGeneralAndAdministrativeExpense",))
        common = set(gross) & set(sga)
        if common:
            opinc = {y: {"value": gross[y]["value"] - sga[y]["value"], "end": y,
                         "start": gross[y]["start"], "filed": gross[y]["filed"],
                         "tag": "GrossProfit-SellingGeneralAndAdministrativeExpense",
                         "form": "10-K"} for y in common}
    capex = annual_values(facts, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"))
    fin_lease_add = annual_values(facts, ("RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability",))
    # Economic CapEx = cash CapEx + finance-lease-funded asset additions. This keeps
    # CapEx consistent with D&A, which already includes finance-lease ROU amortization
    # (`FinanceLeaseRightOfUseAssetAmortization`). Cash purchases and lease principal
    # repayments are not double-counted: additions are a separate non-cash investing flow.
    econ_capex = {}
    for y, c in capex.items():
        add = fin_lease_add[y]["value"] if y in fin_lease_add else 0.0
        econ_capex[y] = {"value": c["value"] + add, "end": c["end"], "start": c["start"],
                         "filed": c["filed"], "form": c["form"], "tag": c["tag"],
                         "finance_lease_additions": add}
    taxes = annual_values(facts, ("IncomeTaxExpenseBenefit",))
    pretax = annual_values(facts, _PRETAX_TAGS)

    years, (rev_v, op_v, cx_v) = _align(revenue, opinc, econ_capex)
    if len(years) > 6:
        years = years[-6:]
        rev_v = rev_v[-6:]
        op_v = op_v[-6:]
        cx_v = cx_v[-6:]
    if len(years) < 2:
        raise ValueError(
            f"Insufficient annual financial history for {ticker} ({len(years)} matched years); "
            f"driver forecast requires at least 2 years of revenue/operating income/capex.")

    # D&A: accounting-aware resolver — prefer consolidated total-D&A, else reconstruct
    # from complete, non-overlapping components; never substitute lease amortization alone.
    from .da import resolve_annual_da, resolve_ttm_da
    da_res = resolve_annual_da(facts, years)
    da_v = [da_res["values"].get(y, 0.0) for y in years]
    da_detail = da_res["detail"]
    da_status = da_res["status"]

    finance_lease_amortization_present = any(
        d["tag"] == "FinanceLeaseRightOfUseAssetAmortization" for d in da_detail)
    finance_lease_additions_available = bool(fin_lease_add)

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
    if da_status == "unavailable":
        warnings.append("Consolidated D&A unavailable; D&A treated as zero (disclosed) — "
                        "never substituting finance-lease amortization alone.")
    elif da_status == "derived":
        warnings.append("Consolidated D&A unavailable; reconstructed from component tags (disclosed).")
    if finance_lease_amortization_present and not finance_lease_additions_available:
        warnings.append(
            "Finance-lease ROU amortization is in D&A but finance-lease-funded CapEx "
            "(`RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability`) is not reported — "
            "unresolved material lease definition; economic CapEx may be understated.")
    if not nwc_present:
        limitations.append("Operating NWC facts unavailable; NWC ratio treated as zero (disclosed).")
    elif any(v is None for v in nwc_series):
        limitations.append("Some fiscal-year NWC observations are missing; only available years used.")
    if len(years) < 6:
        limitations.append(f"Only {len(years)} fiscal years of history (sample-size limitation).")

    # TTM (latest complete trailing-twelve-month period) for the forecast starting point.
    ttm_rev = trailing_twelve_months(facts, _REVENUE_TAGS)
    ttm_opinc = trailing_twelve_months(facts, ("OperatingIncomeLoss",))
    ttm_ocf = trailing_twelve_months(facts, ("NetCashProvidedByUsedInOperatingActivities",))
    ttm_capex = trailing_twelve_months(facts, ("PaymentsToAcquireProductiveAssets",
                                               "PaymentsToAcquirePropertyPlantAndEquipment"))
    ttm_da = resolve_ttm_da(facts)
    ttm = {
        "revenue": ttm_rev["value"] if ttm_rev else None,
        "operating_income": ttm_opinc["value"] if ttm_opinc else None,
        "operating_cash_flow": ttm_ocf["value"] if ttm_ocf else None,
        "capex": ttm_capex["value"] if ttm_capex else None,
        "da": ttm_da.get("value"),
        "da_tag": ttm_da.get("tag"),
        "da_status": ttm_da.get("status"),
        "asof": (ttm_rev or {}).get("ytd_end") or (ttm_rev or {}).get("fy_end"),
        "basis": (ttm_rev or {}).get("basis", "annual"),
    }

    return {
        "ticker": ticker, "company": name, "cik": cik,
        "fiscal_years": years,
        "revenue": rev_v, "operating_income": op_v, "capex": cx_v,
        "da": da_v, "da_detail": da_detail, "da_status": da_status,
        "finance_lease_amortization_present": finance_lease_amortization_present,
        "finance_lease_additions_available": finance_lease_additions_available,
        "effective_tax_rate": tax_v,
        "nwc": nwc_series,
        "nwc_latest": nwc_present[-1] if nwc_present else None,
        "asof": years[-1],
        "ttm": ttm,
        "units": "USD",
        "limitations": limitations,
        "warnings": warnings,
    }
