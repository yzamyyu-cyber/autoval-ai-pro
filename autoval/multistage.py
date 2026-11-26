"""Optional multi-stage DCF: explicit → transition → ROIC-consistent terminal.

The single-stage driver forecast holds capital intensity (and thus the implicit
reinvestment rate) constant into perpetuity, which conflates today's — possibly
elevated — reinvestment phase with the mature steady state. This separate model
fades revenue growth, operating margin and the reinvestment rate from the explicit
forecast (years 1-5) to sustainable mature values over a transition window
(years 6-10), then applies a ROIC-consistent terminal cash flow from year 11 onward:

    reinvestment rate = terminal growth / mature incremental ROIC
    terminal FCFF      = year-11 NOPAT × (1 − reinvestment rate)
    terminal value     = terminal FCFF / (WACC − terminal growth)

It is additive and does NOT change the original five-year DCF. No market price is
used to calibrate any assumption.
"""
from __future__ import annotations
from math import isfinite

DEFAULT_MATURE_ROIC = 0.12   # mature incremental ROIC (return on new investment)
DEFAULT_TRANSITION_YEARS = 5


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def implied_reinvestment_rate(row: dict) -> float | None:
    """Net reinvestment / NOPAT implied by a driver-forecast row.

    net reinvestment = CapEx − D&A + ΔNWC; FCFF = NOPAT − net reinvestment.
    """
    nopat = row.get("nopat")
    if nopat is None or abs(nopat) < 1e-9:
        return None
    net_reinv = (row.get("capex", 0.0) - row.get("da", 0.0)
                 + row.get("change_in_nwc", 0.0))
    return net_reinv / nopat


def _validate(wacc: float, terminal_growth: float, mature_incremental_roic: float,
              transition_years: int) -> None:
    if not (isfinite(wacc) and isfinite(terminal_growth) and isfinite(mature_incremental_roic)):
        raise ValueError("multi-stage DCF inputs must be finite")
    if not 0 < wacc < 1:
        raise ValueError("WACC must be in (0, 1)")
    if not -0.1 <= terminal_growth < wacc:
        raise ValueError("terminal growth must be in [-10%, WACC)")
    if not 0 < mature_incremental_roic < 1:
        raise ValueError("mature incremental ROIC must be in (0, 1)")
    if mature_incremental_roic <= terminal_growth:
        raise ValueError(
            f"mature incremental ROIC ({mature_incremental_roic:.1%}) must exceed terminal "
            f"growth ({terminal_growth:.1%}) so the reinvestment rate stays below 100%")
    if not isinstance(transition_years, int) or transition_years < 1:
        raise ValueError("transition years must be a positive integer")


def _fade(t: int, start: float, end: float, n: int) -> float:
    """Linear fade: step t of n returns start→end (t=0..n-1)."""
    frac = (t + 1) / n
    return start + (end - start) * frac


def multistage_dcf(
    forecast: dict,
    wacc: float,
    terminal_growth: float,
    mature_incremental_roic: float = DEFAULT_MATURE_ROIC,
    transition_years: int = DEFAULT_TRANSITION_YEARS,
    sustainable_margin: float | None = None,
    case: str = "base",
) -> dict:
    """Compute enterprise value under the multi-stage DCF.

    `forecast` is the output of `autoval.forecast.build_forecast` (a {case: {drivers,
    rows}} dict). The explicit years 1-5 come from `forecast[case]["rows"]`; years
    6..6+transition_years-1 transition drivers linearly; year 11 anchors the terminal.
    """
    _validate(wacc, terminal_growth, mature_incremental_roic, transition_years)

    fc = forecast[case]
    explicit = fc["rows"]
    if not explicit:
        raise ValueError("multi-stage DCF requires an explicit forecast")
    drivers = fc["drivers"]
    tax = drivers["normalized_tax_rate"]
    g_explicit = drivers["revenue_growth"]
    m_explicit = drivers["operating_margin"]
    m_sustainable = sustainable_margin if sustainable_margin is not None else m_explicit

    r_sustainable = _clip(terminal_growth / mature_incremental_roic, 0.0, 1.0)

    r_explicit = implied_reinvestment_rate(explicit[-1])
    if r_explicit is None:
        r_explicit = r_sustainable
    r_explicit = _clip(r_explicit, 0.0, 1.5)

    # Transition rows (years 6..6+transition_years-1)
    revenue = explicit[-1]["revenue"]
    transition_rows = []
    for t in range(transition_years):
        g_t = _fade(t, g_explicit, terminal_growth, transition_years)
        m_t = _fade(t, m_explicit, m_sustainable, transition_years)
        r_t = _fade(t, r_explicit, r_sustainable, transition_years)
        revenue = revenue * (1 + g_t)
        nopat = revenue * m_t * (1 - tax)
        fcff = nopat * (1 - r_t)
        transition_rows.append({
            "year": 6 + t, "revenue_growth": g_t, "operating_margin": m_t,
            "reinvestment_rate": r_t, "revenue": revenue, "nopat": nopat,
            "fcff": fcff,
        })

    # Terminal (year 11, first mature year)
    revenue_11 = revenue * (1 + terminal_growth)
    nopat_11 = revenue_11 * m_sustainable * (1 - tax)
    fcff_terminal = nopat_11 * (1 - r_sustainable)
    terminal_value = fcff_terminal / (wacc - terminal_growth)

    # Discount
    all_rows = list(explicit) + transition_rows
    pv_forecast = 0.0
    for t, row in enumerate(all_rows, start=1):
        pv_forecast += row["fcff"] / (1 + wacc) ** t
    n_total = len(all_rows)
    terminal_pv = terminal_value / (1 + wacc) ** n_total
    enterprise_value = pv_forecast + terminal_pv

    return {
        "case": case,
        "wacc": wacc,
        "terminal_growth": terminal_growth,
        "mature_incremental_roic": mature_incremental_roic,
        "transition_years": transition_years,
        "sustainable_margin": m_sustainable,
        "normalized_tax_rate": tax,
        "reinvestment_rate_explicit": r_explicit,
        "reinvestment_rate_terminal": r_sustainable,
        "explicit_rows": explicit,
        "transition_rows": transition_rows,
        "terminal": {
            "year": n_total + 1,
            "revenue_usd": revenue_11,
            "nopat_usd": nopat_11,
            "fcff_usd": fcff_terminal,
            "reinvestment_rate": r_sustainable,
            "terminal_value_usd": terminal_value,
            "pv_terminal_value_usd": terminal_pv,
        },
        "forecast_fcff_usd": [row["fcff"] for row in all_rows],
        "pv_forecast_fcff_usd": pv_forecast,
        "pv_terminal_value_usd": terminal_pv,
        "terminal_weight_of_ev": terminal_pv / enterprise_value if enterprise_value != 0 else None,
        "enterprise_value_usd": enterprise_value,
    }


def multistage_valuation(
    forecast: dict,
    wacc: float,
    terminal_growth: float,
    net_debt: float,
    shares: float,
    mature_incremental_roic: float = DEFAULT_MATURE_ROIC,
    transition_years: int = DEFAULT_TRANSITION_YEARS,
    sustainable_margin: float | None = None,
    case: str = "base",
) -> dict:
    """Multi-stage DCF bridged to equity value per share."""
    if shares <= 0 or not isfinite(float(shares)):
        raise ValueError("shares must be positive and finite")
    d = multistage_dcf(forecast, wacc, terminal_growth, mature_incremental_roic,
                       transition_years, sustainable_margin, case)
    equity = d["enterprise_value_usd"] - net_debt
    d["net_debt_usd"] = net_debt
    d["equity_value_usd"] = equity
    d["shares"] = shares
    d["intrinsic_per_share_usd"] = equity / shares
    return d


def multistage_roic_sensitivity(
    forecast: dict,
    wacc: float,
    terminal_growth: float,
    net_debt: float,
    shares: float,
    roic_values: tuple = (0.08, 0.10, 0.12, 0.15, 0.20),
    transition_years: int = DEFAULT_TRANSITION_YEARS,
    sustainable_margin: float | None = None,
    case: str = "base",
) -> list[dict]:
    """Base-case intrinsic value across mature incremental ROIC assumptions.

    ROIC values at or below terminal growth are skipped (they imply a reinvestment
    rate ≥ 100%, which the model rejects). The 12% default is an assumed parameter,
    not a market-calibrated value.
    """
    rows = []
    for roic in roic_values:
        if roic <= terminal_growth:
            rows.append({"mature_incremental_roic": roic, "valid": False,
                         "reason": "ROIC <= terminal growth", "intrinsic_per_share_usd": None})
            continue
        d = multistage_valuation(forecast, wacc, terminal_growth, net_debt, shares,
                                 mature_incremental_roic=roic,
                                 transition_years=transition_years,
                                 sustainable_margin=sustainable_margin, case=case)
        rows.append({"mature_incremental_roic": roic, "valid": True,
                     "reinvestment_rate_terminal": d["reinvestment_rate_terminal"],
                     "enterprise_value_usd": d["enterprise_value_usd"],
                     "intrinsic_per_share_usd": d["intrinsic_per_share_usd"]})
    return rows
