"""Apply an APPROVED correction to a SEPARATE analysis snapshot.

The original extraction is never mutated: `apply_correction` deep-copies it, overwrites
only the corrected financial metric (net debt / total debt / cash), and recomputes the
derived debt metrics via the deterministic engine. It returns the corrected snapshot plus
the before/after impact so the original and corrected analyses remain distinguishable.
"""
from __future__ import annotations
from copy import deepcopy
from math import isfinite


def _classify_metric(definition: str, category: str) -> str:
    d = (definition or "").lower()
    c = (category or "").lower()
    if "net debt" in d or "net_debt" in d or "netdebt" in d:
        return "net_debt"
    # "debt less cash" / "net of cash" / "after cash" describe a NET debt figure (cash is
    # already deducted); must NOT be classified as gross debt (which would subtract cash again).
    if ("debt" in d and ("less cash" in d or "net of cash" in d or "after cash" in d
                         or "after deducting cash" in d or "less cash and" in d)):
        return "net_debt"
    if "cash" in d and "debt" not in d:
        return "cash_and_equivalents"
    if "cash" in c and "restricted" in c:
        return "cash_and_equivalents"
    # A single debt COMPONENT (short-term borrowings, commercial paper, current portion,
    # finance lease) is NOT a complete total/net debt figure and must not be applied as one.
    for component_kw in ("short-term borrowing", "short term borrowing", "commercial paper",
                        "current portion", "current-portion", "finance lease",
                        "capital lease", "notes payable", "loans payable"):
        if component_kw in d:
            return "component"
    return "total_debt"


def apply_correction(extraction: dict, proposal: dict) -> dict:
    """Return {original, corrected, impact} where `corrected` is a NEW extraction dict."""
    definition = proposal.get("financial_definition") or ""
    category = proposal.get("category", "")
    proposed = proposal.get("proposed_financial_value")

    # A debt COMPONENT (short-term borrowings, commercial paper, current portion, finance
    # lease) is not a complete total/net debt figure; refuse to apply it as one.
    if _classify_metric(definition, category) == "component":
        return {"status": "unsupported_component",
                "reason": ("proposal describes a single debt component, not a complete "
                           "total/net debt figure")}


    rec = (extraction.get("source") or {}).get("debt_reconciliation") or {}
    original_net_debt = rec.get("net_debt") if "net_debt" in rec else extraction.get("net_debt")
    original_total_debt = rec.get("total_debt") if "total_debt" in rec else extraction.get("total_debt")
    cash = rec.get("cash_and_equivalents") if "cash_and_equivalents" in rec else extraction.get("cash_and_equivalents")
    shares = extraction.get("shares")

    metric = _classify_metric(definition, category)

    corrected = deepcopy(extraction)
    corrected_net_debt = original_net_debt
    corrected_total_debt = original_total_debt

    if proposed is not None and isfinite(float(proposed)):
        pv = float(proposed)
        if metric == "net_debt":
            corrected_net_debt = pv
            corrected_total_debt = (pv + cash) if (cash is not None) else original_total_debt
        elif metric == "cash_and_equivalents":
            corrected_total_debt = original_total_debt
            corrected_net_debt = (original_total_debt - pv) if original_total_debt is not None else None
            corrected["cash_and_equivalents"] = pv
        else:  # total_debt
            corrected_total_debt = pv
            corrected_net_debt = (pv - cash) if cash is not None else None

    corrected["net_debt"] = corrected_net_debt
    corrected["total_debt"] = corrected_total_debt
    if rec:
        rec2 = deepcopy(rec)
        rec2["net_debt"] = corrected_net_debt
        rec2["total_debt"] = corrected_total_debt
        if metric == "cash_and_equivalents":
            rec2["cash_and_equivalents"] = pv
        rec2["corrected_by_reconciliation"] = True
        corrected.setdefault("source", {})["debt_reconciliation"] = rec2

    delta = (corrected_net_debt - original_net_debt) if (
        corrected_net_debt is not None and original_net_debt is not None) else None
    impact = {
        "metric": metric,
        "original_net_debt": original_net_debt,
        "corrected_net_debt": corrected_net_debt,
        "original_total_debt": original_total_debt,
        "corrected_total_debt": corrected_total_debt,
        "net_debt_delta": delta,
        "per_share_impact_usd": ((original_net_debt - corrected_net_debt) / shares)
                                 if (delta is not None and shares) else None,
    }
    return {"original": extraction, "corrected": corrected, "impact": impact}
