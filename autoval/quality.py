"""Valuation reliability classification (reusable, explainable).

Classifier states:
  - AVAILABLE:       required inputs present and reconciliation checks pass; the
                     DCF headline is presentable (model-risk warnings may still
                     be surfaced).
  - LOW_CONFIDENCE:  a calculation exists, but financial-data-quality concerns
                     prevent presenting it as a reliable headline estimate.
  - UNSUITABLE:      a calculation exists, but the BASE case is objectively
                     invalid (negative enterprise value or negative equity), so
                     it cannot support a headline valuation. The mechanical
                     estimate is preserved for audit. A negative bear/bull
                     scenario alone is only a warning, not a headline failure.
  - UNAVAILABLE:     required inputs/calculations are missing or invalid.

Three concerns are kept separate:
  - arithmetic:      performed independently by `verify_output.py` (Decimal
                     recomputation); NOT recomputed here.
  - data_quality:    input-provenance concerns that lower confidence.
  - model_suitability + unsuitability:
                     model-risk warnings vs. objective "unsuitable" conditions.

Consumers that read a saved analysis.json missing the "quality" field label the
result "Not assessed" — they must not imply it passed this policy.

The policy never uses the market-price gap as a signal, never hardcodes a ticker,
and treats thresholds as configurable model-risk heuristics, not financial
formulas. Negative growth alone is a warning, never an automatic failure.
"""
from __future__ import annotations

# Configurable model-risk heuristics. These are review thresholds, not financial
# formulas; adjust per-call or as the methodology evolves.
TERMINAL_WEIGHT_LIMIT = 0.80   # terminal value > 80% of EV => excessive perpetuity dependence
MIN_FISCAL_YEARS = 6           # forecast uses trailing-3-year ratios; <6 years is a small sample
WEAK_FCFF_MARGIN_LIMIT = 0.03  # base FCFF < 3% of revenue every year => fragile perpetuity
REINVESTMENT_IMBALANCE_LIMIT = 0.05  # capex_ratio − da_ratio above this => heavy net reinvestment


def _fcff_margins(a: dict) -> list[float]:
    """Base-case FCFF as a fraction of revenue, year by year (when available)."""
    base = a["scenarios"]["base"]
    fcff = base.get("forecast_fcff_usd") or []
    rows = ((a.get("forecast") or {}).get("base") or {}).get("rows") or []
    if not fcff or len(rows) != len(fcff):
        return []
    margins = []
    for cf, row in zip(fcff, rows):
        rev = row.get("revenue")
        if rev:
            margins.append(cf / rev)
    return margins


def assess_valuation_quality(
    result: dict,
    terminal_weight_limit: float = TERMINAL_WEIGHT_LIMIT,
    min_fiscal_years: int = MIN_FISCAL_YEARS,
    weak_fcff_margin_limit: float = WEAK_FCFF_MARGIN_LIMIT,
    reinvestment_imbalance_limit: float = REINVESTMENT_IMBALANCE_LIMIT,
) -> dict:
    a = result.get("analysis")
    if a is None:
        return {"state": "unavailable",
                "reasons": ["no analysis result was produced"],
                "data_quality": [], "model_suitability": [], "unsuitability": []}

    base = a["scenarios"]["base"]
    data_quality: list[str] = []
    model_suitability: list[str] = []
    unsuitability: list[str] = []
    is_demo = result.get("mode") == "demo"

    # ---- UNAVAILABLE (invalid required inputs) ----
    fcff = base.get("forecast_fcff_usd") or []
    if fcff and all(c <= 0 for c in fcff):
        return {"state": "unavailable",
                "reasons": ["forecast free cash flow is non-positive for every forecast year"],
                "data_quality": [], "model_suitability": [], "unsuitability": []}
    if not base.get("shares") or base["shares"] <= 0:
        return {"state": "unavailable",
                "reasons": ["share count is missing or non-positive"],
                "data_quality": [], "model_suitability": [], "unsuitability": []}

    # ---- DATA-QUALITY concerns (affect confidence) ----

    # 1. Company-specific WACC missing (live mode only; the offline demo is an
    #    intentionally illustrative example, not a company-specific valuation).
    wacc_block = result.get("wacc")
    if not is_demo and (wacc_block is None or not wacc_block.get("available")):
        data_quality.append("company-specific WACC unavailable; an illustrative discount rate was used")

    fin = (result.get("provenance") or {}).get("financials") or {}

    # 2. Debt reconciliation contains assumed/stale components (material uncertainty).
    for e in fin.get("excluded_debt_tags") or []:
        if e.get("status") in ("included_in_total", "stale"):
            data_quality.append(f"debt component '{e.get('tag')}' is {e.get('status')} "
                                f"(current/noncurrent split assumed or stale)")
            break

    # 2b. Unresolved material lease definition: finance-lease amortization is in D&A but
    #     finance-lease-funded CapEx is not reported, so economic CapEx is understated.
    hist = result.get("forecast_history") or {}
    if hist.get("finance_lease_amortization_present") and not hist.get("finance_lease_additions_available"):
        data_quality.append(
            "finance-lease amortization is in D&A but finance-lease-funded CapEx is not reported "
            "(unresolved material lease definition; economic CapEx may be understated)")

    # 3. Share count from a consolidated fallback tag (class-agnostic approximation).
    if fin.get("shares", {}).get("tag") == "CommonStockSharesOutstanding":
        data_quality.append("share count is a consolidated us-gaap figure (class-agnostic approximation)")

    # 4. Small historical sample.
    if hist.get("fiscal_years") and len(hist["fiscal_years"]) < min_fiscal_years:
        data_quality.append(f"fewer than {min_fiscal_years} fiscal years of history")

    # ---- MODEL UNSUITABILITY (base case invalid; suppress headline, preserve value) ----
    # Only a negative BASE case invalidates the headline valuation. A negative
    # bear/bull scenario is a downside/upside warning, not a headline failure.

    base_ev = base.get("enterprise_value_usd")
    base_eq = base.get("equity_value_usd")
    if base_ev is not None and base_ev < 0:
        unsuitability.append(
            "base case has a negative enterprise value "
            "(its discounted free cash flow is non-positive — invalid terminal economics)")
    elif base_eq is not None and base_eq < 0:
        unsuitability.append(
            "base case has a negative equity value "
            "(enterprise value does not cover net debt; equity is a limited-liability claim)")

    scenarios = a.get("scenarios") or {}
    negative_ev_scen = sorted(c for c, s in scenarios.items()
                              if c != "base" and (s.get("enterprise_value_usd") or 0) < 0)
    negative_eq_scen = sorted(c for c, s in scenarios.items()
                              if c != "base" and (s.get("equity_value_usd") or 0) < 0)
    margins = _fcff_margins(a)
    thin_fcff = bool(margins and all(m > 0 for m in margins)
                     and max(margins) < weak_fcff_margin_limit)

    # A negative downside scenario combined with persistently thin base FCFF is a
    # material, unresolved model limitation (the perpetuity is fragile and the downside
    # economics are invalid) — reviewed, not presented as a reliable headline.
    if (negative_ev_scen or negative_eq_scen) and thin_fcff:
        unsuitability.append(
            f"{', '.join(negative_ev_scen or negative_eq_scen)} scenario has negative "
            f"enterprise/equity value AND base free cash flow is persistently thin "
            f"(below {weak_fcff_margin_limit:.0%} of revenue) — the forecast model cannot "
            f"support a reliable headline valuation")

    # ---- MODEL-SUITABILITY heuristics (warnings only; do NOT suppress) ----

    # 5a. A negative non-base scenario is a downside/upside warning, not a headline failure.
    if negative_ev_scen and not (negative_ev_scen and thin_fcff):
        model_suitability.append(
            f"{', '.join(negative_ev_scen)} scenario has a negative enterprise value "
            f"(downside/upside economics are invalid; the base case is unaffected)")
    elif negative_eq_scen and not (negative_eq_scen and thin_fcff):
        model_suitability.append(
            f"{', '.join(negative_eq_scen)} scenario has a negative equity value "
            f"(downside/upside economics are invalid; the base case is unaffected)")

    # 5b. Persistently thin base FCFF. Thin cash-flow margins can be economically
    #     valid, but they make the perpetuity fragile — surfaced as a warning when
    #     not already escalated to a material limitation above.
    if thin_fcff and not (negative_ev_scen or negative_eq_scen):
        model_suitability.append(
            f"base free cash flow is persistently thin (below {weak_fcff_margin_limit:.0%} of revenue "
            f"in every forecast year); this can be economically valid but makes the perpetuity fragile")

    # 5. Negative first-year FCFF (perpetuity formula is economically fragile).
    if fcff and fcff[0] <= 0:
        model_suitability.append("free cash flow is negative in the first forecast year")

    # 6. Non-positive forecast revenue growth (constant-growth terminal fits poorly).
    forecast = a.get("forecast")
    if forecast:
        g = forecast["base"]["drivers"].get("revenue_growth")
        if g is not None and g <= 0:
            model_suitability.append("forecast revenue growth is non-positive")

    # 7. Excessive terminal-value dependence.
    tw = base.get("terminal_weight_of_ev")
    if tw is not None and tw > terminal_weight_limit:
        model_suitability.append(
            f"terminal value is {tw:.0%} of enterprise value "
            f"(exceeds {terminal_weight_limit:.0%} — most value rests on the perpetuity)")

    # 8. Inconsistent reinvestment: heavy net reinvestment paired with low terminal growth.
    drivers = (forecast or {}).get("base", {}).get("drivers") or {}
    capex_ratio = drivers.get("capex_ratio")
    da_ratio = drivers.get("da_ratio")
    terminal_growth = base.get("terminal_growth")
    if (capex_ratio is not None and da_ratio is not None
            and capex_ratio - da_ratio > reinvestment_imbalance_limit
            and terminal_growth is not None and terminal_growth <= 0.03):
        model_suitability.append(
            f"reinvestment assumption is internally inconsistent: CapEx is "
            f"{capex_ratio - da_ratio:.0%} of revenue above D&A yet terminal growth is only "
            f"{terminal_growth:.0%} (heavy reinvestment should not be paired with minimal growth)")

    reasons = data_quality + unsuitability + model_suitability
    if unsuitability:
        state = "unsuitable"
    elif data_quality:
        state = "low_confidence"
    else:
        state = "available"
    return {"state": state, "reasons": reasons,
            "data_quality": data_quality, "model_suitability": model_suitability,
            "unsuitability": unsuitability}


def assess_multistage_quality(result: dict) -> dict:
    """Quality assessment for the multi-stage DCF.

    A new forecast model must NOT remove unresolved source-data limitations, so
    `data_quality` is inherited unchanged from the single-stage assessment. Only the
    model-suitability signals are re-evaluated against the multi-stage terminal
    economics (ROIC-consistent terminal) rather than the single-stage perpetuity.
    """
    base_q = assess_valuation_quality(result)
    data_quality = base_q["data_quality"]
    unavailable = base_q["state"] == "unavailable"

    ms = (result.get("analysis") or {}).get("multistage") or {}
    base = ms.get("base") or {}
    model_suitability: list[str] = []
    unsuitability: list[str] = []

    if base:
        tw = base.get("terminal_weight_of_ev")
        if tw is not None and tw > TERMINAL_WEIGHT_LIMIT:
            model_suitability.append(
                f"multi-stage terminal value is {tw:.0%} of enterprise value "
                f"(exceeds {TERMINAL_WEIGHT_LIMIT:.0%})")
        if (base.get("enterprise_value_usd") or 0) < 0:
            unsuitability.append("multi-stage base case has a negative enterprise value")
        elif (base.get("equity_value_usd") or 0) < 0:
            unsuitability.append("multi-stage base case has a negative equity value")
        roic = (ms.get("assumptions") or {}).get("mature_incremental_roic")
        wacc = base.get("wacc")
        if roic is not None and wacc is not None and roic < wacc:
            model_suitability.append(
                f"mature incremental ROIC ({roic:.0%}) is below WACC ({wacc:.1%}); "
                f"terminal reinvestment is value-destructive (assumed parameter)")

    if unavailable:
        state = "unavailable"
    elif unsuitability:
        state = "unsuitable"
    elif data_quality:
        state = "low_confidence"
    else:
        state = "available"
    return {"state": state, "reasons": data_quality + unsuitability + model_suitability,
            "data_quality": data_quality, "model_suitability": model_suitability,
            "unsuitability": unsuitability}
