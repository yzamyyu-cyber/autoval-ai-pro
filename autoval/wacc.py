"""Pure WACC calculations and metadata assembly. No network I/O.

All rates are decimals (0.05 == 5%). Data retrieval lives in `wacc_data.py`; this
module only does deterministic math so it can be unit-tested in isolation.
"""
from __future__ import annotations
from math import isfinite


def _num(v) -> float:
    return float(v)


def cost_of_equity(risk_free: float, beta: float, erp: float) -> float:
    """CAPM cost of equity: rf + beta * ERP."""
    rf, b, e = _num(risk_free), _num(beta), _num(erp)
    if not all(isfinite(x) for x in (rf, b, e)):
        raise ValueError("Cost of equity inputs must be finite")
    return rf + b * e


def after_tax_cost_of_debt(pre_tax_cost: float, marginal_tax_rate: float) -> float:
    """After-tax cost of debt using a MARGINAL tax rate (not the effective rate)."""
    rd, t = _num(pre_tax_cost), _num(marginal_tax_rate)
    if not isfinite(rd) or not isfinite(t):
        raise ValueError("After-tax cost of debt inputs must be finite")
    if not 0 <= t <= 1:
        raise ValueError("Marginal tax rate must be in [0, 1]")
    if rd < 0:
        raise ValueError("Pre-tax cost of debt must be non-negative")
    return rd * (1 - t)


def capital_weights(equity_value: float, debt_value: float) -> tuple[float, float]:
    """Market-value capital weights (we, wd). Debt book value proxies market value."""
    e, d = _num(equity_value), _num(debt_value)
    if not isfinite(e) or not isfinite(d) or e < 0 or d < 0:
        raise ValueError("Equity and debt values must be finite and non-negative")
    total = e + d
    if total <= 0:
        raise ValueError("Capital base must be positive")
    return e / total, d / total


def wacc(equity_value: float, debt_value: float, cost_eq: float,
         cost_debt_at: float) -> tuple[float, float, float]:
    """Return (wacc, equity_weight, debt_weight)."""
    we, wd = capital_weights(equity_value, debt_value)
    re, rd = _num(cost_eq), _num(cost_debt_at)
    if re <= 0:
        raise ValueError("Cost of equity must be positive")
    if rd < 0:
        raise ValueError("After-tax cost of debt must be non-negative")
    return we * re + wd * rd, we, wd


def beta_ols(x_returns: list[float], y_returns: list[float]) -> dict:
    """OLS regression of y on x WITH intercept.

    Returns {"beta", "alpha", "r_squared", "se_beta", "n"}.
    `x_returns`/`y_returns` are simple-period returns (not log) of market and stock.
    """
    x = [_num(v) for v in x_returns]
    y = [_num(v) for v in y_returns]
    n = len(x)
    if n < 3:
        raise ValueError("Need at least 3 observations for a regression")
    if len(y) != n:
        raise ValueError("x and y must have the same length")
    xm = sum(x) / n
    ym = sum(y) / n
    sxx = sum((xi - xm) ** 2 for xi in x)
    syy = sum((yi - ym) ** 2 for yi in y)
    sxy = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, y))
    if sxx == 0:
        raise ValueError("Zero variance in market returns; beta undefined")
    beta = sxy / sxx
    alpha = ym - beta * xm
    resid = [yi - (alpha + beta * xi) for xi, yi in zip(x, y)]
    ss_res = sum(r * r for r in resid)
    r_squared = 1.0 - ss_res / syy if syy > 0 else 0.0
    dof = n - 2
    se_resid = (ss_res / dof) ** 0.5 if dof > 0 else float("inf")
    se_beta = se_resid / (sxx ** 0.5) if sxx > 0 else float("inf")
    return {"beta": beta, "alpha": alpha, "r_squared": r_squared,
            "se_beta": se_beta, "n": n}


def compute_wacc(risk_free: float, beta: float, erp: float, equity_value: float,
                 debt_value: float, pre_tax_cost_of_debt: float,
                 marginal_tax_rate: float) -> dict:
    """Assemble the full WACC from numeric inputs. Returns intermediate values too."""
    re = cost_of_equity(risk_free, beta, erp)
    rd_at = after_tax_cost_of_debt(pre_tax_cost_of_debt, marginal_tax_rate)
    w, we, wd = wacc(equity_value, debt_value, re, rd_at)
    return {
        "risk_free_rate": _num(risk_free),
        "beta": _num(beta),
        "equity_risk_premium": _num(erp),
        "cost_of_equity": re,
        "pre_tax_cost_of_debt": _num(pre_tax_cost_of_debt),
        "marginal_tax_rate": _num(marginal_tax_rate),
        "after_tax_cost_of_debt": rd_at,
        "equity_value": _num(equity_value),
        "debt_value": _num(debt_value),
        "equity_weight": we,
        "debt_weight": wd,
        "wacc": w,
    }
