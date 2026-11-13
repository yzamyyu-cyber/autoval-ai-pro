"""Deterministic DCF calculations. All cash flows, debt and EV are in USD."""
from __future__ import annotations
from math import isfinite


def fcff_from_us_gaap_cashflows(cfo: float, capex: float, interest_expense: float, tax_rate: float) -> float:
    """Approximate unlevered FCF: US-GAAP CFO - capex + after-tax interest.

    This is not a universally exact FCFF definition. Requires review of interest
    classification and any nonoperating items in the relevant filing.
    All monetary inputs are positive cash outflows for capex/interest.
    """
    vals = (cfo, capex, interest_expense, tax_rate)
    if not all(isfinite(float(v)) for v in vals):
        raise ValueError("Cash flow inputs must be finite")
    if capex < 0 or interest_expense < 0 or not 0 <= tax_rate <= 0.5:
        raise ValueError("Capex and interest must be nonnegative; tax rate must be between 0 and 50%")
    return cfo - capex + interest_expense * (1 - tax_rate)


def dcf_fcff(last_fcff: float, shares: float, net_debt: float, growth: float,
             wacc: float, terminal_growth: float, years: int = 5) -> dict:
    """Project a constant-growth, five-year FCFF enterprise DCF and equity bridge."""
    fields = (last_fcff, shares, net_debt, growth, wacc, terminal_growth)
    if not all(isfinite(float(v)) for v in fields):
        raise ValueError("DCF inputs must be finite numbers")
    if last_fcff <= 0 or shares <= 0 or years not in range(1, 21):
        raise ValueError("DCF requires positive starting FCFF and share count; 1-20 forecast years")
    if growth <= -1 or not 0 < wacc < 1 or not -0.1 <= terminal_growth < wacc:
        raise ValueError("Invalid DCF assumption: need growth > -100% and -10% <= terminal growth < WACC < 100%")
    projected = [last_fcff * (1 + growth)**t for t in range(1, years + 1)]
    present_values = [cf / (1 + wacc)**t for t, cf in enumerate(projected, start=1)]
    terminal_cf = projected[-1] * (1 + terminal_growth)
    terminal_value = terminal_cf / (wacc - terminal_growth)
    terminal_pv = terminal_value / (1 + wacc)**years
    enterprise_value = sum(present_values) + terminal_pv
    equity_value = enterprise_value - net_debt
    return {
        "growth": growth, "wacc": wacc, "terminal_growth": terminal_growth,
        "years": years, "starting_fcff_usd": last_fcff,
        "forecast_fcff_usd": projected, "pv_forecast_fcff_usd": present_values,
        "pv_terminal_value_usd": terminal_pv,
        "terminal_weight_of_ev": terminal_pv / enterprise_value,
        "enterprise_value_usd": enterprise_value,
        "net_debt_usd": net_debt, "equity_value_usd": equity_value,
        "shares": shares, "intrinsic_per_share_usd": equity_value / shares,
    }


def dcf_from_fcff(fcff_stream, shares: float, net_debt: float, wacc: float,
                  terminal_growth: float) -> dict:
    """Discount a pre-computed FCFF stream (driver forecast) to enterprise value.

    Unlike `dcf_fcff` (constant growth), the stream is supplied year-by-year and each
    element is discounted individually; the terminal value uses the final stream FCFF.
    """
    stream = [float(c) for c in fcff_stream]
    if not stream or any(not isfinite(c) for c in stream):
        raise ValueError("FCFF stream must contain finite values")
    if shares <= 0 or not 0 < wacc < 1 or not -0.1 <= terminal_growth < wacc:
        raise ValueError("Invalid DCF inputs: shares>0, 0<wacc<1, -10%<=terminal_growth<wacc")
    years = len(stream)
    pv = [c / (1 + wacc) ** t for t, c in enumerate(stream, start=1)]
    terminal_cf = stream[-1] * (1 + terminal_growth)
    terminal_value = terminal_cf / (wacc - terminal_growth)
    terminal_pv = terminal_value / (1 + wacc) ** years
    enterprise_value = sum(pv) + terminal_pv
    equity_value = enterprise_value - net_debt
    return {
        "years": years,
        "forecast_fcff_usd": stream,
        "pv_forecast_fcff_usd": pv,
        "pv_terminal_value_usd": terminal_pv,
        "terminal_weight_of_ev": terminal_pv / enterprise_value,
        "enterprise_value_usd": enterprise_value,
        "net_debt_usd": net_debt,
        "equity_value_usd": equity_value,
        "shares": shares,
        "intrinsic_per_share_usd": equity_value / shares,
        "wacc": wacc, "terminal_growth": terminal_growth,
    }


def derive_scenarios(fcff_history: list[float], wacc: float | None = None) -> dict:
    """Transparent policy assumptions.

    Growth and terminal growth remain scenario parameters (Bear/Base/Bull). WACC is
    either a single company-specific rate applied to all three scenarios, or — when no
    company-specific WACC is supplied — the illustrative 11/10/9% policy.
    """
    if not fcff_history or fcff_history[-1] <= 0:
        raise ValueError("Latest FCFF must be positive; DCF is unsupported otherwise")
    selected = [float(x) for x in fcff_history[-3:]]
    if len(selected) >= 2 and selected[0] > 0:
        historical_growth = (selected[-1] / selected[0]) ** (1 / (len(selected) - 1)) - 1
        base_growth = max(0.02, min(0.10, historical_growth))
        growth_origin = "Clipped CAGR of up to three positive annual FCFF observations, bounded to 2%-10%"
    else:
        base_growth = 0.04
        growth_origin = "4% policy fallback because fewer than two positive FCFF observations"

    if wacc is not None:
        if not isfinite(float(wacc)) or not 0 < float(wacc) < 1:
            raise ValueError("Company WACC must be a finite rate in (0, 1)")
        scenario_wacc = float(wacc)
        discount_origin = "Company-specific WACC (single rate applied to all scenarios; see WACC block)"
    else:
        scenario_wacc = None
        discount_origin = "Illustrative fixed policy WACC (11%/10%/9%); NOT market-calibrated company WACC"

    bear_wacc = scenario_wacc if scenario_wacc is not None else 0.11
    base_wacc = scenario_wacc if scenario_wacc is not None else 0.10
    bull_wacc = scenario_wacc if scenario_wacc is not None else 0.09
    for w, tg in ((bear_wacc, 0.015), (base_wacc, 0.020), (bull_wacc, 0.025)):
        if w <= tg:
            raise ValueError(f"WACC ({w:.4f}) must exceed terminal growth ({tg:.4f})")

    return {
        "bear": {"growth": max(-0.10, base_growth - 0.05), "wacc": bear_wacc, "terminal_growth": 0.015},
        "base": {"growth": base_growth, "wacc": base_wacc, "terminal_growth": 0.020},
        "bull": {"growth": min(0.18, base_growth + 0.05), "wacc": bull_wacc, "terminal_growth": 0.025},
        "growth_origin": growth_origin,
        "discount_origin": discount_origin,
    }


def sensitivity_table(last_fcff: float, shares: float, net_debt: float, base_growth: float,
                      wacc_values: list[float], terminal_growth_values: list[float]) -> list[dict]:
    """Grid of intrinsic value per share over WACC × terminal growth (WACC > terminal g)."""
    table = []
    for tg in terminal_growth_values:
        for w in wacc_values:
            if w <= tg:
                continue
            r = dcf_fcff(last_fcff, shares, net_debt, base_growth, w, tg)
            table.append({"wacc": w, "terminal_growth": tg,
                          "intrinsic_per_share_usd": r["intrinsic_per_share_usd"],
                          "enterprise_value_usd": r["enterprise_value_usd"]})
    return table


def equity_bridge(enterprise_value: float, total_debt: float, cash: float,
                  short_term_investments: float = 0.0,
                  restricted_investments: float | None = None,
                  restricted_in_short_term: float | None = None,
                  long_term_investments: float | None = None,
                  other_claims: float = 0.0) -> dict:
    """Transparent enterprise-to-equity bridge including nonoperating investments.

    equity = operating EV - total debt + cash + eligible nonoperating securities - other claims.

    Eligible nonoperating securities are reported as a RANGE because the restricted
    portion *within* short-term investments is typically disclosed only in the filing
    note, not as a standalone XBRL fact:

      - conservative: short-term investments minus ALL reported restricted investments
        (may over-subtract when some restrictions sit in excluded long-term/equity
        investments -- deliberately conservative).
      - upper:        the full short-term investments balance (assumes all qualify as
        nonoperating and unrestricted -- an upper bound, not a verified value).
      - reconciled:   short-term investments minus `restricted_in_short_term`, supplied
        only when that note-derived amount has been independently verified.
    """
    if not all(isfinite(float(v)) for v in (enterprise_value, total_debt, cash, short_term_investments)):
        raise ValueError("Bridge inputs must be finite numbers")
    if total_debt < 0 or cash < 0 or short_term_investments < 0 or other_claims < 0:
        raise ValueError("Debt, cash, investments, and other claims must be non-negative")

    st = float(short_term_investments)
    rest = None if restricted_investments is None else float(restricted_investments)
    if rest is not None and rest < 0:
        raise ValueError("restricted_investments must be non-negative")
    lt = None if long_term_investments is None else float(long_term_investments)

    eligible_upper = st
    eligible_conservative = st if rest is None else max(0.0, st - rest)
    eligible = {"conservative": eligible_conservative, "upper": eligible_upper}
    base_equity = enterprise_value - total_debt + cash  # cash-only reference
    equity = {"conservative": base_equity + eligible_conservative - other_claims,
              "upper": base_equity + eligible_upper - other_claims}

    notes = [
        "Upper bound assumes the entire short-term investments balance is nonoperating and unrestricted; it is not a verified valuation.",
    ]
    if rest is None:
        notes.append("Restricted investments not reported/verifiable; conservative bound equals upper bound (restriction amount unknown).")
    else:
        notes.append("Conservative bound subtracts the full restricted-investments balance; some restrictions may belong to excluded long-term investments, so this bound may understate eligible securities.")

    result = {
        "operating_enterprise_value_usd": enterprise_value,
        "total_debt_usd": total_debt,
        "cash_and_equivalents_usd": cash,
        "short_term_investments_usd": st,
        "restricted_investments_total_usd": rest,
        "long_term_investments_usd": lt,
        "other_claims_usd": other_claims,
        "eligible_nonoperating_securities_usd": eligible,
        "equity_value_usd_cash_only": base_equity,
        "equity_value_usd": equity,
        "notes": notes,
    }
    if restricted_in_short_term is not None:
        ris = float(restricted_in_short_term)
        if ris < 0 or ris > st:
            raise ValueError("restricted_in_short_term must be within [0, short_term_investments]")
        eligible["reconciled"] = st - ris
        equity["reconciled"] = base_equity + (st - ris) - other_claims
        result["restricted_in_short_term_usd"] = ris
        result["reconciled_basis"] = "restricted_in_short_term supplied (note-verified)"
    else:
        result["restricted_in_short_term_usd"] = None
    return result


def analyze_valuation(stock: dict, wacc: float | None = None) -> dict:
    required = ("market_price", "shares", "net_debt", "fcff_history")
    missing = [key for key in required if key not in stock]
    if missing:
        raise ValueError(f"Missing valuation inputs: {', '.join(missing)}")
    hist = [float(row["fcff_usd"]) for row in stock["fcff_history"]]
    policy = derive_scenarios(hist, wacc)
    # Intrinsic value per share uses the diluted share count when available, else the
    # point-in-time common share count (difference disclosed below).
    shares_for_intrinsic = stock.get("diluted_shares") or stock["shares"]
    results = {case: dcf_fcff(hist[-1], shares_for_intrinsic, stock["net_debt"], **policy[case])
               for case in ("bear", "base", "bull")}
    price = float(stock["market_price"])
    if price <= 0 or not isfinite(price):
        raise ValueError("Market price must be positive")
    for case in results:
        results[case]["upside_vs_price_pct"] = (results[case]["intrinsic_per_share_usd"] / price - 1) * 100
    if any(results[k]["intrinsic_per_share_usd"] > results[k2]["intrinsic_per_share_usd"]
           for k,k2 in (("bear","base"),("base","bull"))):
        raise ValueError("Scenario ordering is inconsistent; review assumptions")

    # Enterprise-to-equity bridge: add eligible nonoperating securities when the
    # debt/cash split is available (live mode). Eligible securities are reported as a
    # range (conservative/upper), with a reconciled case only when note-verified.
    bridge = None
    limitations = [
        "FCFF cash-flow approach is an approximation requiring filing-level review.",
        "The model assumes constant annual FCFF growth over five years.",
        "Terminal value can dominate intrinsic value; review sensitivity.",
        "Filing figures and market quotes may have different as-of dates.",
        "No automatic buy/sell instruction or live trading is provided.",
    ]
    total_debt = stock.get("total_debt")
    cash_and_equiv = stock.get("cash_and_equivalents")
    if total_debt is not None and cash_and_equiv is not None:
        st = stock.get("short_term_investments") or 0.0
        rest = stock.get("restricted_investments")
        lt = stock.get("long_term_investments")
        ris = stock.get("restricted_in_short_term")
        bridge = equity_bridge(results["base"]["enterprise_value_usd"], total_debt,
                               cash_and_equiv, st, rest, ris, lt)
        for case, r in results.items():
            b = equity_bridge(r["enterprise_value_usd"], total_debt, cash_and_equiv,
                              st, rest, ris, lt)
            r["intrinsic_per_share_usd_cash_only"] = r["intrinsic_per_share_usd"]
            for variant, eq in b["equity_value_usd"].items():
                r[f"intrinsic_per_share_usd_{variant}"] = eq / shares_for_intrinsic
        limitations.append(
            "Nonoperating investments are included in the equity bridge as a conservative-to-upper "
            "range because the restricted portion within short-term investments is disclosed only in "
            "the filing note; the upper bound is not a verified valuation and the reconciled case "
            "requires note verification.")

    sensitivity = None
    if wacc is not None:
        base_growth = policy["base"]["growth"]
        wacc_values = [round(max(0.02, wacc + d), 6) for d in (-0.015, -0.010, 0.0, 0.010, 0.015)]
        terminal_values = [0.015, 0.020, 0.025]
        sensitivity = sensitivity_table(hist[-1], shares_for_intrinsic, stock["net_debt"],
                                        base_growth, wacc_values, terminal_values)

    return {"ticker": stock["ticker"], "market_price": price,
            "price_date": stock.get("price_date"), "financial_asof": stock.get("financial_asof"),
            "scenarios": results, "assumption_provenance": {
                "growth": policy["growth_origin"], "wacc": policy["discount_origin"],
                "terminal_growth": "Illustrative policy rates 1.5%, 2.0%, 2.5% respectively"},
            "bridge": bridge,
            "sensitivity": sensitivity,
            "wacc_basis": "company-specific" if wacc is not None else "illustrative",
            "shares_outstanding": stock["shares"],
            "diluted_shares": stock.get("diluted_shares"),
            "limitations": limitations}


def analyze_driver_valuation(stock: dict, history: dict, wacc: float | None = None) -> dict:
    """Driver-based five-year FCFF valuation (replaces constant-growth for v5).

    `history` is the normalized historical driver table from forecast_data.retrieve_history.
    Bear/Base/Bull differ by driver assumptions only; the same company WACC is applied.
    """
    from .forecast import build_forecast
    forecasts = build_forecast(history)
    shares = stock.get("diluted_shares") or stock["shares"]
    net_debt = stock["net_debt"]
    price = float(stock["market_price"])
    if price <= 0 or not isfinite(price):
        raise ValueError("Market price must be positive")
    terminal = {"bear": 0.015, "base": 0.020, "bull": 0.025}

    results = {}
    for case in ("bear", "base", "bull"):
        stream = [r["fcff"] for r in forecasts[case]["rows"]]
        d = dcf_from_fcff(stream, shares, net_debt, wacc, terminal[case])
        d["upside_vs_price_pct"] = (d["intrinsic_per_share_usd"] / price - 1) * 100
        results[case] = d
    if any(results[k]["intrinsic_per_share_usd"] > results[k2]["intrinsic_per_share_usd"]
           for k, k2 in (("bear", "base"), ("base", "bull"))):
        raise ValueError("Driver scenario ordering inconsistent; review driver assumptions")

    bridge = None
    total_debt = stock.get("total_debt")
    cash_and_equiv = stock.get("cash_and_equivalents")
    if total_debt is not None and cash_and_equiv is not None:
        st_ = stock.get("short_term_investments") or 0.0
        rest = stock.get("restricted_investments")
        lt = stock.get("long_term_investments")
        ris = stock.get("restricted_in_short_term")
        bridge = equity_bridge(results["base"]["enterprise_value_usd"], total_debt,
                               cash_and_equiv, st_, rest, ris, lt)
        for case, r in results.items():
            b = equity_bridge(r["enterprise_value_usd"], total_debt, cash_and_equiv,
                              st_, rest, ris, lt)
            r["intrinsic_per_share_usd_cash_only"] = r["intrinsic_per_share_usd"]
            for variant, eq in b["equity_value_usd"].items():
                r[f"intrinsic_per_share_usd_{variant}"] = eq / shares

    sensitivity = []
    if wacc is not None:
        base_stream = [r["fcff"] for r in forecasts["base"]["rows"]]
        for tg in (0.015, 0.020, 0.025):
            for wv in (round(max(0.02, wacc + d), 6) for d in (-0.015, -0.010, 0.0, 0.010, 0.015)):
                if wv <= tg:
                    continue
                dd = dcf_from_fcff(base_stream, shares, net_debt, wv, tg)
                sensitivity.append({"wacc": wv, "terminal_growth": tg,
                                    "intrinsic_per_share_usd": dd["intrinsic_per_share_usd"]})

    # Capex-intensity sensitivity: persistent-high-investment case (FY-latest capex ratio).
    from .forecast import capex_stats, forecast_with_capex
    capex_meta = capex_stats(history)
    capex_sensitivity = None
    high_capex = capex_meta.get("fy_latest")
    if high_capex is not None:
        alt = forecast_with_capex(history, high_capex)
        capex_sensitivity = {
            "capex_ratio_cases": capex_meta,
            "high_capex_ratio": high_capex,
            "label": "Persistent-high-CapEx sensitivity (FY-latest capex intensity), not an established forecast.",
            "intrinsic_per_share_usd": {},
        }
        for case in ("bear", "base", "bull"):
            stream = [r["fcff"] for r in alt[case]]
            d = dcf_from_fcff(stream, shares, net_debt, wacc, terminal[case])
            capex_sensitivity["intrinsic_per_share_usd"][case] = d["intrinsic_per_share_usd"]

    limitations = [
        "Driver-based FCFF forecast; drivers are derived from historical ratios/trends, not forward guidance.",
        "Normalized operating tax rate is a documented baseline, separate from the WACC marginal tax rate.",
        "Operating NWC ratio uses the latest fiscal-year-end balance sheet (a single point rather than a multi-year average).",
        "The model assumes driver ratios are stable over five years; scenario spreads are rule-based.",
        "No automatic buy/sell instruction or live trading is provided.",
    ]
    return {
        "ticker": stock["ticker"], "market_price": price,
        "price_date": stock.get("price_date"), "financial_asof": history.get("asof"),
        "scenarios": results,
        "forecast": forecasts,
        "assumption_provenance": {
            "method": "Driver-based five-year forecast (Revenue -> EBIT -> NOPAT -> FCFF)",
            "wacc": "Company-specific WACC (single rate across scenarios)" if wacc is not None
                    else "Illustrative fixed policy WACC",
            "terminal_growth": "1.5% / 2.0% / 2.5% (Bear/Base/Bull), separate from operating growth",
        },
        "bridge": bridge,
        "sensitivity": sensitivity,
        "capex_sensitivity": capex_sensitivity,
        "wacc_basis": "company-specific" if wacc is not None else "illustrative",
        "shares_outstanding": stock["shares"],
        "diluted_shares": stock.get("diluted_shares"),
        "limitations": limitations,
    }


def observed_multiples(stock: dict) -> dict:
    """Observed multiples only; not a standalone peer-relative valuation."""
    price, shares = stock["market_price"], stock["shares"]
    ev = price * shares + stock["net_debt"]
    ebit, da, income = stock.get("ebit"), stock.get("depreciation"), stock.get("net_income")
    ebitda = None if ebit is None or da is None else ebit + da
    return {"market_enterprise_value_usd": ev,
            "ev_to_ebitda": ev / ebitda if ebitda is not None and ebitda > 0 else None,
            "price_to_earnings": price * shares / income if income is not None and income > 0 else None,
            "note": "Observed ratios, not peer-derived fair values. Peer valuation is a future feature."}
