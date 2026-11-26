"""Dependency-aware regeneration of a valuation after an approved correction.

Applying a correction changes more than a single number: debt/cash flows into capital
weights, WACC, the five-year and multi-stage DCF, the reverse-DCF anchor, comparables and
quality. `regenerate_analysis` re-runs the whole deterministic pipeline on the CORRECTED
stock (a deep copy), reusing only the unchanged market price history and financial-driver
history. The original result is never mutated.
"""
from __future__ import annotations
from copy import deepcopy
from math import isfinite

from autoval.finance import analyze_driver_valuation, analyze_valuation, observed_multiples
from autoval.wacc import compute_wacc
from autoval.market_data import classify_wacc


def recompute_wacc(corrected_stock: dict, original_wacc_block: dict | None) -> dict:
    """Recompute WACC from the corrected debt/equity using the original market-calibrated
    risk-free rate, ERP and beta. Reuses the original inputs envelope; only the capital
    structure (equity value, debt value, cost-of-debt proxy) is recomputed."""
    inp = (original_wacc_block or {}).get("inputs") or {}
    if not inp or not (original_wacc_block or {}).get("available"):
        return {"available": False, "reason": "no original WACC inputs to recompute", "inputs": inp}

    rf = inp.get("risk_free_rate", {}).get("value")
    erp = inp.get("equity_risk_premium", {}).get("value")
    beta = inp.get("beta", {}).get("value")
    tax = inp.get("marginal_tax_rate", {}).get("value", 0.21)
    if rf is None or erp is None or beta is None:
        return {"available": False, "reason": "missing rf/erp/beta inputs", "inputs": inp}

    price = corrected_stock.get("market_price")
    shares = corrected_stock.get("shares")
    equity_value = price * shares if (price and shares and float(price) > 0 and float(shares) > 0) else None
    debt = corrected_stock.get("total_debt")
    records = (corrected_stock.get("source") or {}).get("annual_records") or []
    interest = records[-1].get("interest", {}).get("value") if records else None
    if equity_value is None or not debt or not interest:
        return {"available": False,
                "reason": "cannot recompute WACC (missing equity value / debt / interest)",
                "inputs": inp}

    pre_tax_cod = float(interest) / float(debt)
    calc = compute_wacc(float(rf), float(beta), float(erp), float(equity_value),
                        float(debt), pre_tax_cod, float(tax))
    new_inp = deepcopy(inp)
    new_inp["equity_value"] = {"value": equity_value, "available": True, "kind": "calculated"}
    new_inp["debt_value"] = {"value": float(debt), "available": True, "kind": "observed"}
    new_inp["pre_tax_cost_of_debt"] = {"value": pre_tax_cod, "available": True, "kind": "calculated"}
    return {"available": True, "wacc": calc["wacc"], "calculation": calc, "inputs": new_inp}


def regenerate_analysis(original_result: dict, corrected_stock: dict,
                        user_agent: str = "") -> dict:
    """Re-run the full valuation on the corrected stock; return a NEW result dict.

    Reuses: market price history (technical), financial-driver forecast history, and market
    source. Recomputes: WACC, five-year DCF, multi-stage DCF, reverse-DCF inputs, observed
    multiples, relative valuation, sensitivity, quality and provenance.
    """
    ticker = corrected_stock.get("ticker") or original_result.get("ticker")
    mode = original_result.get("mode", "live")

    # 1. WACC (dependency: total_debt -> capital weights + cost of debt).
    wacc_block = recompute_wacc(corrected_stock, original_result.get("wacc"))
    company_wacc = wacc_block["wacc"] if wacc_block.get("available") else None

    # 2. Valuation (five-year + multi-stage + TTM + sensitivity). Forecast drivers are
    #    unchanged by a balance-sheet correction, so the driver history is reused.
    forecast_history = original_result.get("forecast_history")
    if forecast_history is not None:
        valuation = analyze_driver_valuation(corrected_stock, forecast_history, company_wacc)
    else:
        valuation = analyze_valuation(corrected_stock, company_wacc)

    observed = observed_multiples(corrected_stock)

    # 3. Relative valuation (best-effort).
    relative = None
    if mode == "live":
        try:
            from autoval.peers import peer_groups
            from autoval.relative_data import build_relative_valuation
            from autoval.relative import summarize_relative_valuation
            pgroups = peer_groups(ticker)
            if pgroups:
                rel = build_relative_valuation(ticker, user_agent, pgroups,
                                               target_price=corrected_stock.get("market_price"),
                                               target_price_date=corrected_stock.get("price_date"),
                                               target_market_mode=original_result.get("market_mode", "current"))
                relative = {"groups": summarize_relative_valuation(rel["target"], rel["peers"], pgroups),
                            "target": rel["target"], "peer_map": pgroups}
        except Exception:
            relative = None

    # 4. Assemble the corrected result (a deep copy, so the original is preserved).
    result = deepcopy(original_result)
    result["analysis"] = valuation
    result["multiples"] = observed
    result["wacc"] = wacc_block
    result["relative"] = relative
    result["provenance"]["financials"] = corrected_stock.get("source", result["provenance"]["financials"])
    result["reconciled"] = True

    # WACC basis: company-specific only when beta + equity value are genuine.
    wi = (wacc_block or {}).get("inputs") or {}
    beta_avail = bool(wi.get("beta", {}).get("available"))
    equity_avail = bool(wi.get("equity_value", {}).get("available"))
    result["wacc_basis"] = classify_wacc(wacc_block, beta_avail, equity_avail)

    from autoval.quality import assess_valuation_quality
    result["quality"] = assess_valuation_quality(result)
    from autoval.provenance import build_provenance
    result["evidence"] = build_provenance(result)
    return result
