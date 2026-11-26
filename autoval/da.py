"""Accounting-aware D&A resolver (reusable).

Consolidated total depreciation & amortization is preferred. Component reconstruction is
used ONLY when the total is unavailable AND the core `Depreciation` component is present
for the trailing forecast window (so a lone finance-lease ROU amortization is never
substituted for consolidated D&A). Lease amortization already inside the total tag is never
double-counted.

Recovery paths (both reusable, not ticker-specific):
  - cross-period tag migration : an issuer that once tagged its D&A line as `Depreciation`
    and later migrated to a combined total tag is merged (validated by overlap equality).
  - component reconstruction  : Depreciation + intangible amortization (annual or
    quarterly-summed) + finance-lease ROU amortization, non-overlapping.

Statuses:
  - consolidated : used the consolidated total-D&A tag (or a validated migration merge).
  - derived      : reconstructed from complete, non-overlapping components.
  - unavailable  : no reliable D&A (never invented).
"""
from __future__ import annotations

from .sec import annual_values, concept
from .ttm import trailing_twelve_months

DA_TOTAL_TAGS = ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                 "DepreciationAmortizationAndAccretionNet")
DA_MIGRATION_TAG = "Depreciation"
DA_AMORTIZATION_TAGS = ("AmortizationOfIntangibleAssets", "FiniteLivedIntangibleAssetsAmortizationExpense")
DA_COMPONENT_TAGS = ("AmortizationOfIntangibleAssets",
                     "FinanceLeaseRightOfUseAssetAmortization")


def _annual_from_quarters(facts: dict, tags: tuple[str, ...], years: list[str],
                          unit: str = "USD") -> dict:
    """Reconstruct fiscal-year sums from ~3-month 10-Q facts (for issuers that do not
    report an annual fact under the tag, e.g. Alphabet's intangible amortization)."""
    out: dict = {}
    for tag in tags:
        raw = concept(facts, "us-gaap", tag, unit)
        by_year: dict = {}
        for e in raw:
            if e.get("form") not in ("10-Q", "10-Q/A"):
                continue
            start, end = e.get("start"), e.get("end")
            if not start or not end:
                continue
            fy_end = end[:4]
            # only the three-month increments (avoid double-counting the YTD 9-month facts)
            from datetime import date
            try:
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except (TypeError, ValueError):
                continue
            if not (60 <= days <= 100):
                continue
            if fy_end not in by_year:
                by_year[fy_end] = {}
            by_year[fy_end][end] = float(e["val"])
        # map fiscal-year-end string -> the full fiscal year (calendar FY = end[:4])
        for fy_end, quarters in by_year.items():
            # sum the distinct quarter-ends (dedupe by quarter-end date)
            total = sum(quarters.values())
            # find the matching aligned year (year[-4:] == fy_end)
            for y in years:
                if y[:4] == fy_end:
                    out[y] = {"value": total, "tag": tag, "basis": "quarterly_sum"}
    return out


def resolve_annual_da(facts: dict, years: list[str], unit: str = "USD") -> dict:
    """Resolve annual D&A for each fiscal year in `years`.

    Returns {"values": {year: value}, "detail": [{tag, year|years_present, basis}], "status"}.
    """
    # 1. Prefer consolidated total D&A (annual_values merges tag migrations).
    total = annual_values(facts, DA_TOTAL_TAGS, unit=unit)
    vals = {y: total[y]["value"] for y in years if y in total}
    if len(vals) == len(years):
        detail = [{"tag": total[y]["tag"], "year": y, "basis": "consolidated"} for y in sorted(vals)]
        return {"values": vals, "detail": detail, "status": "consolidated"}

    dep = annual_values(facts, (DA_MIGRATION_TAG,), unit=unit)

    # 2. Cross-period tag migration: `Depreciation` was the issuer's D&A line before it
    #    migrated to a combined total tag. Validated by overlap equality (Depreciation ==
    #    total in the years both are reported), confirming negligible amortization.
    overlap = [y for y in years if y in total and y in dep]
    if overlap:
        equal = all(abs(dep[y]["value"] - total[y]["value"])
                    <= 0.01 * max(abs(total[y]["value"]), 1.0) for y in overlap)
        if equal:
            merged = {}
            detail = []
            for y in years:
                if y in total:
                    merged[y] = total[y]["value"]
                    detail.append({"tag": total[y]["tag"], "year": y, "basis": "consolidated"})
                elif y in dep:
                    merged[y] = dep[y]["value"]
                    detail.append({"tag": "Depreciation", "year": y,
                                   "basis": "consolidated (pre-migration tag)"})
            if len(merged) == len(years):
                return {"values": merged, "detail": detail, "status": "consolidated"}

    # 3. Component reconstruction. Completeness gate: the core `Depreciation` component must
    #    cover the trailing 3-year forecast window (the driver uses the last 3 D&A ratios).
    dep_vals = {y: dep[y]["value"] for y in years if y in dep}
    recent = years[-3:]
    if not all(y in dep_vals for y in recent):
        return {"values": {}, "detail": [
                    {"tag": "Depreciation", "years_present": sorted(dep_vals)}],
                "status": "unavailable"}

    values = {y: dep_vals.get(y, 0.0) for y in years}
    detail = [{"tag": "Depreciation", "years_present": sorted(dep_vals), "basis": "component"}]

    # Intangible amortization: annual fact first, else quarterly-summed.
    amort = annual_values(facts, DA_AMORTIZATION_TAGS, unit=unit)
    if not amort:
        amort = _annual_from_quarters(facts, DA_AMORTIZATION_TAGS, years, unit)
    if amort:
        for y in years:
            if y in amort:
                values[y] += amort[y]["value"]
        detail.append({"tag": "AmortizationOfIntangibleAssets",
                       "years_present": sorted(amort), "basis": "component"})

    # Finance-lease ROU amortization (non-overlapping with Depreciation / PP&E).
    fl = annual_values(facts, ("FinanceLeaseRightOfUseAssetAmortization",), unit=unit)
    if fl:
        for y in years:
            if y in fl:
                values[y] += fl[y]["value"]
        detail.append({"tag": "FinanceLeaseRightOfUseAssetAmortization",
                       "years_present": sorted(fl), "basis": "component"})

    return {"values": values, "detail": detail, "status": "derived"}


def resolve_ttm_da(facts: dict, unit: str = "USD") -> dict:
    """Resolve trailing-twelve-month D&A. Prefers the consolidated total tag with the
    most recent reporting period (avoids a stale tag that an issuer has since migrated
    away from, e.g. Walmart's DepreciationDepletionAndAmortization after FY2019)."""
    best = None
    for tag in DA_TOTAL_TAGS:
        r = trailing_twelve_months(facts, (tag,))
        if r and r.get("value"):
            period = r.get("ytd_end") or r.get("fy_end") or ""
            if best is None or period > best["_period"]:
                best = {"value": r["value"], "tag": tag, "status": "consolidated",
                        "asof": period, "_period": period}
    if best:
        best.pop("_period", None)
        return best

    total = 0.0
    used = []
    for tag in ("Depreciation",) + DA_COMPONENT_TAGS:
        r = trailing_twelve_months(facts, (tag,))
        if r and r.get("value"):
            total += r["value"]
            used.append(tag)
    return {"value": (total if used else None), "tag": "+".join(used),
            "status": ("derived" if used else "unavailable"),
            "asof": None}
