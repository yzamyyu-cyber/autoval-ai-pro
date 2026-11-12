"""Deterministic driver-based five-year FCFF forecasting. No network I/O.

The forecast replaces the constant-growth policy with a revenue-driven model:

    Revenue_t  = Revenue_{t-1} * (1 + g_t)
    EBIT_t     = Revenue_t * operating_margin_t
    NOPAT_t    = EBIT_t * (1 - normalized_tax_rate_t)
    D&A_t      = Revenue_t * D&A_ratio_t
    CapEx_t    = Revenue_t * CapEx_ratio_t
    NWC_t      = Revenue_t * NWC_ratio_t
    dNWC_t     = NWC_t - NWC_{t-1}
    FCFF_t     = NOPAT_t + D&A_t - CapEx_t - dNWC_t

All driver derivation is rule-based and traceable (no invented point values).
"""
from __future__ import annotations
from math import isfinite


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _mean(xs) -> float:
    xs = [float(x) for x in xs]
    return sum(xs) / len(xs) if xs else 0.0


def _cagr(values) -> float | None:
    if len(values) < 2 or float(values[0]) <= 0 or float(values[-1]) <= 0:
        return None
    return (float(values[-1]) / float(values[0])) ** (1 / (len(values) - 1)) - 1


def _seq(x, n):
    return list(x) if isinstance(x, (list, tuple)) else [x] * n


def project_fcff(base_revenue: float, base_nwc: float, years: int,
                 revenue_growth, operating_margin, normalized_tax_rate,
                 da_ratio, capex_ratio, nwc_ratio) -> list[dict]:
    """Project `years` annual FCFF rows from driver ratios.

    `base_nwc` is the NWC at the start of the forecast (the latest actual NWC);
    `base_revenue` is the latest actual annual revenue. An increase in NWC reduces FCFF.
    """
    if base_revenue <= 0 or years < 1:
        raise ValueError("base_revenue must be positive and years >= 1")
    if not isfinite(float(base_nwc)):
        raise ValueError("base_nwc must be finite")
    g = _seq(revenue_growth, years)
    m = _seq(operating_margin, years)
    t = _seq(normalized_tax_rate, years)
    da = _seq(da_ratio, years)
    cx = _seq(capex_ratio, years)
    nw = _seq(nwc_ratio, years)
    for name, arr in (("margin", m), ("tax", t), ("da", da), ("capex", cx), ("nwc", nw)):
        if any(not isfinite(float(v)) for v in arr):
            raise ValueError(f"{name} drivers must be finite")
    if any(not 0 <= v <= 1 for v in t):
        raise ValueError("normalized tax rate must be in [0, 1]")
    if any(v < 0 for v in cx):
        raise ValueError("capex ratio must be non-negative")

    rows = []
    revenue = float(base_revenue)
    nwc_prev = float(base_nwc)
    for i in range(years):
        revenue = revenue * (1 + g[i])
        ebit = revenue * m[i]
        nopat = ebit * (1 - t[i])
        d_a = revenue * da[i]
        capex = revenue * cx[i]
        nwc = revenue * nw[i]
        d_nwc = nwc - nwc_prev
        fcff = nopat + d_a - capex - d_nwc
        rows.append({
            "year": i + 1,
            "revenue": revenue,
            "revenue_growth": g[i],
            "operating_margin": m[i],
            "ebit": ebit,
            "normalized_tax_rate": t[i],
            "nopat": nopat,
            "da": d_a,
            "da_ratio": da[i],
            "capex": capex,
            "capex_ratio": cx[i],
            "nwc": nwc,
            "nwc_ratio": nw[i],
            "change_in_nwc": d_nwc,
            "fcff": fcff,
        })
        nwc_prev = nwc
    return rows


def derive_scenario_drivers(history: dict) -> dict:
    """Derive Bear/Base/Bull driver assumptions from a `history` dict (see
    forecast_data.retrieve_history). Rules are documented and traceable."""
    rev = history["revenue"]
    opinc = history["operating_income"]
    da = history["da"]
    capex = history["capex"]
    nwc = history.get("nwc")

    g_base = _cagr(rev[-3:]) if len(rev) >= 3 else _cagr(rev)
    g_base = _clip(g_base if g_base is not None else 0.02, -0.05, 0.25)

    margins = [o / r for o, r in zip(opinc, rev) if r > 0]
    m_base = _clip(_mean(margins[-3:]) if margins else 0.20, 0.0, 0.60)

    da_ratio = _mean([d / r for d, r in zip(da[-3:], rev[-3:]) if r > 0]) or 0.0
    capex_ratio = _mean([c / r for c, r in zip(capex[-3:], rev[-3:]) if r > 0]) or 0.0
    nwc_last = next((v for v in reversed(nwc) if v is not None), None) if nwc else None
    nwc_ratio = (nwc_last / rev[-1]) if nwc_last is not None and rev[-1] > 0 else 0.0

    tax = 0.21  # normalized operating tax rate (documented baseline)

    return {
        "base": {"revenue_growth": g_base, "operating_margin": m_base,
                 "normalized_tax_rate": tax, "da_ratio": da_ratio,
                 "capex_ratio": capex_ratio, "nwc_ratio": nwc_ratio},
        "bear": {"revenue_growth": _clip(g_base - 0.03, -0.10, 0.30),
                 "operating_margin": m_base - 0.03,
                 "normalized_tax_rate": tax,
                 "da_ratio": da_ratio * 1.05,
                 "capex_ratio": capex_ratio * 1.15,
                 "nwc_ratio": nwc_ratio},
        "bull": {"revenue_growth": _clip(g_base + 0.03, -0.10, 0.30),
                 "operating_margin": m_base + 0.03,
                 "normalized_tax_rate": tax,
                 "da_ratio": da_ratio * 0.95,
                 "capex_ratio": capex_ratio * 0.90,
                 "nwc_ratio": nwc_ratio},
    }


def build_forecast(history: dict, years: int = 5) -> dict:
    """Return {case: {"drivers": {...}, "rows": [...], "base_revenue": ..., "base_nwc": ...}}."""
    drivers = derive_scenario_drivers(history)
    base_revenue = history["revenue"][-1]
    nwc_series = history.get("nwc")
    base_nwc = next((v for v in reversed(nwc_series) if v is not None), 0.0) if nwc_series else 0.0
    out = {}
    for case, d in drivers.items():
        rows = project_fcff(base_revenue, base_nwc, years, **d)
        out[case] = {"drivers": d, "rows": rows, "base_revenue": base_revenue, "base_nwc": base_nwc}
    return out


def capex_stats(history: dict) -> dict:
    """Capex/revenue ratios: 3-year mean (base), latest FY, 6-year mean and median."""
    rev = history["revenue"]
    capex = history["capex"]
    ratios = [c / r for c, r in zip(capex, rev) if r > 0]

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    def median(xs):
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2 if n else None

    return {
        "three_year_mean": mean(ratios[-3:]) if len(ratios) >= 3 else None,
        "fy_latest": ratios[-1] if ratios else None,
        "six_year_mean": mean(ratios) if ratios else None,
        "six_year_median": median(ratios) if ratios else None,
    }


def forecast_with_capex(history: dict, capex_ratio: float, years: int = 5) -> dict:
    """Recompute forecasts applying a single capex ratio to every scenario (sensitivity)."""
    drivers = derive_scenario_drivers(history)
    base_revenue = history["revenue"][-1]
    nwc_series = history.get("nwc")
    base_nwc = next((v for v in reversed(nwc_series) if v is not None), 0.0) if nwc_series else 0.0
    out = {}
    for case, d in drivers.items():
        d2 = dict(d)
        d2["capex_ratio"] = capex_ratio
        out[case] = project_fcff(base_revenue, base_nwc, years, **d2)
    return out
