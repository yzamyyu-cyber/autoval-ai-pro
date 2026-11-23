"""Infer the constant growth after forecast year one that matches a share price."""
from __future__ import annotations

from math import isfinite

from .finance import dcf_from_fcff

MIN_GROWTH = -0.90
MAX_GROWTH = 1.00
PRICE_TOLERANCE = 0.01


def reverse_dcf(report: dict, price: float | None = None) -> dict:
    """Use a saved analysis's base WACC, terminal growth, shares and net debt.

    Anchor forecast year one to the base DCF. Solve a single compounded FCFF
    growth rate for the remaining forecast years. A positive anchor and a valid
    positive terminal multiplier make price strictly increasing in that rate.
    """
    analysis = report["analysis"]
    base = analysis["scenarios"]["base"]
    target = float(analysis["market_price"] if price is None else price)
    forecast = base["forecast_fcff_usd"]
    if len(forecast) < 2:
        raise ValueError("Reverse DCF needs at least two forecast years.")

    first_fcff = forecast[0]
    shares = base["shares"]
    wacc = base["wacc"]
    terminal = base["terminal_growth"]
    net_debt = base["net_debt_usd"]
    if not all(isfinite(v) for v in (first_fcff, shares, wacc, terminal, net_debt, target)):
        raise ValueError("Reverse DCF requires finite inputs.")
    if first_fcff <= 0 or target <= 0 or shares <= 0:
        raise ValueError("Reverse DCF requires positive year-one FCFF, target price and share count.")
    if not 0 < wacc < 1 or not -.1 <= terminal < wacc:
        raise ValueError("Reverse DCF requires a valid WACC above terminal growth.")

    def price_at(rate):
        stream = [first_fcff * (1 + rate) ** year for year in range(len(forecast))]
        return dcf_from_fcff(stream, shares, net_debt, wacc, terminal)["intrinsic_per_share_usd"]

    lower, upper = MIN_GROWTH, MAX_GROWTH
    low_price, high_price = price_at(lower), price_at(upper)
    if not (isfinite(low_price) and isfinite(high_price) and low_price < high_price):
        raise ValueError("Reverse DCF could not establish a finite, increasing price range.")
    if not low_price <= target <= high_price:
        raise ValueError(
            f"No match within {lower:.0%} to {upper:.0%} growth. "
            f"That range yields ${low_price:,.2f} to ${high_price:,.2f} per share."
        )

    for _ in range(100):
        rate = (lower + upper) / 2
        modeled_price = price_at(rate)
        if abs(modeled_price - target) <= .000001:
            break
        if modeled_price < target:
            lower = rate
        else:
            upper = rate

    price_error = modeled_price - target
    if abs(price_error) >= PRICE_TOLERANCE:
        raise ValueError("Reverse DCF did not reproduce the target within one cent per share.")

    last_fcff = forecast[-1]
    base_cagr = ((last_fcff / first_fcff) ** (1 / (len(forecast) - 1)) - 1
                 if isfinite(last_fcff) and last_fcff > 0 else None)
    return {
        "ticker": report["ticker"],
        "mode": report["mode"],
        "analysis_run_utc": report.get("run_utc"),
        "financial_asof": analysis.get("financial_asof"),
        "target_price_usd": target,
        "target_source": "analysis" if price is None else "user input",
        "price_date": analysis.get("price_date") if price is None else None,
        "implied_fcff_growth": rate,
        "base_forecast_fcff_cagr": base_cagr,
        "forecast_years": len(forecast),
        "first_year_fcff_usd": first_fcff,
        "wacc": wacc,
        "wacc_basis": analysis.get("wacc_basis"),
        "terminal_growth": terminal,
        "net_debt_usd": net_debt,
        "shares": shares,
        "modeled_price_usd": modeled_price,
        "price_error_usd": price_error,
        "tolerance_usd": PRICE_TOLERANCE,
        "min_growth": MIN_GROWTH,
        "max_growth": MAX_GROWTH,
    }
