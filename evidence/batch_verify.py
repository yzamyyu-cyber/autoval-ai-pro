#!/usr/bin/env python3
"""Batch independent verification: 7 tickers × {annual, TTM} × {5yr, multistage} ×
{bear, base, bull} = 84 combinations.

Independently recomputes FCFF (from drivers), WACC (from market inputs), the 5-year DCF
and the multi-stage DCF (transition + ROIC terminal), and the equity bridge — WITHOUT
importing autoval valuation functions or reusing the engine's computed FCFF/terminal/
intrinsic. Compares to the engine's values and writes evidence/reference_comparison.csv.

Usage: .venv/bin/python evidence/batch_verify.py
"""
from __future__ import annotations
import csv
import json
import os
import sys

# allow importing autoval (repo root) when invoked from evidence/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- independent math (no autoval) ----
def project_fcff(drivers, base_rev, base_nwc, years=5):
    g = drivers["revenue_growth"]; m = drivers["operating_margin"]
    tax = drivers["normalized_tax_rate"]; dr = drivers["da_ratio"]
    cr = drivers["capex_ratio"]; nr = drivers["nwc_ratio"]
    rev, nwc = base_rev, base_nwc
    rows = []
    for _ in range(years):
        rev = rev * (1 + g)
        ebit = rev * m
        nopat = ebit * (1 - tax)
        da = rev * dr
        capex = rev * cr
        n = rev * nr
        d_nwc = n - nwc
        rows.append({"rev": rev, "nopat": nopat, "fcff": nopat + da - capex - d_nwc,
                     "capex": capex, "da": da, "d_nwc": d_nwc})
        nwc = n
    return rows


def recompute_wacc(inp):
    rf = inp["risk_free_rate"]["value"]; beta = inp["beta"]["value"]
    erp = inp["equity_risk_premium"]["value"]; eq = inp["equity_value"]["value"]
    debt = inp["debt_value"]["value"]; cod = inp["pre_tax_cost_of_debt"]["value"]
    tax = inp["marginal_tax_rate"]["value"]
    coe = rf + beta * erp
    wacc = coe * eq / (eq + debt) + cod * (1 - tax) * debt / (eq + debt)
    return coe, cod, wacc


def discount(stream, wacc, tg):
    pv = sum(cf / (1 + wacc) ** t for t, cf in enumerate(stream, start=1))
    tv = stream[-1] * (1 + tg) / (wacc - tg)
    ev = pv + tv / (1 + wacc) ** len(stream)
    return ev


def five_yr_intrinsic(rows, wacc, tg, net_debt, shares):
    ev = discount([r["fcff"] for r in rows], wacc, tg)
    return (ev - net_debt) / shares


def multistage_intrinsic(rows, drivers, wacc, tg, net_debt, shares, roic=0.12, trans=5):
    """Explicit 5yr + transition + ROIC-consistent terminal (independent)."""
    tax = drivers["normalized_tax_rate"]
    m_explicit = drivers["operating_margin"]
    g_explicit = drivers["revenue_growth"]
    r_sustainable = max(0.0, min(1.0, tg / roic))
    last = rows[-1]
    r_explicit = (last["capex"] - last["da"] + last["d_nwc"]) / last["nopat"] if last["nopat"] else r_sustainable
    r_explicit = max(0.0, min(1.5, r_explicit))
    m_sustainable = m_explicit
    rev = last["rev"]
    stream = [r["fcff"] for r in rows]
    for t in range(trans):
        frac = (t + 1) / trans
        g_t = g_explicit + (tg - g_explicit) * frac
        m_t = m_explicit + (m_sustainable - m_explicit) * frac
        r_t = r_explicit + (r_sustainable - r_explicit) * frac
        rev = rev * (1 + g_t)
        nopat = rev * m_t * (1 - tax)
        stream.append(nopat * (1 - r_t))
    nopat_11 = rev * (1 + tg) * m_sustainable * (1 - tax)
    fcff_terminal = nopat_11 * (1 - r_sustainable)
    tv = fcff_terminal / (wacc - tg)
    pv = sum(cf / (1 + wacc) ** t for t, cf in enumerate(stream, start=1))
    ev = pv + tv / (1 + wacc) ** len(stream)
    return (ev - net_debt) / shares


# ---- snapshot generation (uses autoval; generation only, not verification) ----
def build_snapshot(ticker, snap_path):
    from autoval.sec import get_sec_financials
    from autoval.forecast_data import retrieve_history
    from autoval.finance import analyze_driver_valuation
    from autoval.wacc import compute_wacc
    snap = json.load(open(snap_path))
    wi = snap["wacc"]["inputs"]
    stock = get_sec_financials(ticker, os.environ["SEC_USER_AGENT"])
    hist = retrieve_history(ticker, os.environ["SEC_USER_AGENT"])
    debt = stock["total_debt"]
    interest = stock["source"]["annual_records"][-1]["interest"]["value"]
    wacc = compute_wacc(wi["risk_free_rate"]["value"], wi["beta"]["value"],
                        wi["equity_risk_premium"]["value"], wi["equity_value"]["value"],
                        debt, interest / debt, wi["marginal_tax_rate"]["value"])["wacc"]
    stock["market_price"] = snap["analysis"]["market_price"]
    stock["price_date"] = snap["analysis"]["price_date"]
    val = analyze_driver_valuation(stock, hist, wacc)
    return {
        "ticker": ticker,
        "analysis": val,
        "wacc": {"inputs": {
            "risk_free_rate": {"value": wi["risk_free_rate"]["value"]},
            "beta": {"value": wi["beta"]["value"]},
            "equity_risk_premium": {"value": wi["equity_risk_premium"]["value"]},
            "equity_value": {"value": wi["equity_value"]["value"]},
            "debt_value": {"value": debt},
            "pre_tax_cost_of_debt": {"value": interest / debt},
            "marginal_tax_rate": {"value": wi["marginal_tax_rate"]["value"]},
        }},
    }


def verify_ticker(snapshot, rows):
    a = snapshot["analysis"]
    coe, cod, wacc = recompute_wacc(snapshot["wacc"]["inputs"])
    wacc_engine = a["scenarios"]["base"]["wacc"]
    rows.append([snapshot["ticker"], "n/a", "wacc", "n/a", wacc_engine, wacc,
                 abs(wacc - wacc_engine), "PASS" if abs(wacc - wacc_engine) < 1e-9 else "FAIL", ""])

    bases = {"annual": a["scenarios"], "ttm": (a.get("ttm") or {})}
    for basis, scenarios in bases.items():
        if not scenarios:
            continue
        forecast = a["forecast"] if basis == "annual" else (a.get("ttm") or {}).get("forecast", {})
        ms = a.get("multistage") if basis == "annual" else (a.get("ttm") or {}).get("multistage")
        for case in ("bear", "base", "bull"):
            if case not in scenarios or case not in forecast:
                continue
            fc = forecast[case]
            rows5 = project_fcff(fc["drivers"], fc["base_revenue"], fc["base_nwc"])
            sc = scenarios[case]
            indep = five_yr_intrinsic(rows5, sc["wacc"], sc["terminal_growth"],
                                      sc["net_debt_usd"], sc["shares"])
            _record(rows, snapshot["ticker"], basis, "5yr", case, sc["intrinsic_per_share_usd"], indep)

            ms_case = (ms or {}).get(case)
            if ms_case:
                indep_ms = multistage_intrinsic(rows5, fc["drivers"], ms_case["wacc"],
                                                ms_case["terminal_growth"], ms_case["net_debt_usd"],
                                                ms_case["shares"])
                _record(rows, snapshot["ticker"], basis, "multistage", case,
                        ms_case["intrinsic_per_share_usd"], indep_ms)


def _record(rows, t, basis, model, case, eng, indep):
    diff = abs(eng - indep)
    status = "PASS" if diff < 0.01 else "FAIL"
    rows.append([t, basis, model, case, eng, indep, diff, status, ""])


SNAPSHOTS = {
    "MSFT": "/Users/yumin/Downloads/AutoVal_AI_Starter/outputs/workswarm_msft_v8/analysis.json",
    "AMZN": "outputs/amzn_audit/analysis.json",
    "AAPL": "/tmp/aapl_diag/analysis.json",
    "HD": "/Users/yumin/Downloads/AutoVal_AI_Starter/outputs/hd_fresh_skill/analysis.json",
    "GOOGL": "/tmp/googl_v2/analysis.json",
    "TSLA": "/tmp/tsla_v2/analysis.json",
    "NVDA": "outputs/nvda_audit/analysis.json",
}


def main():
    rows = [["ticker", "basis", "model", "scenario", "autoval_value", "independent_value",
             "absolute_difference", "status", "reason"]]
    for t, sp in SNAPSHOTS.items():
        if not os.path.exists(sp):
            rows.append([t, "n/a", "n/a", "n/a", "", "", "", "UNAVAILABLE", f"missing snapshot {sp}"])
            continue
        snap = build_snapshot(t, sp)
        verify_ticker(snap, rows)
    with open("evidence/reference_comparison.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    total = len(rows) - 1
    passed = sum(1 for r in rows[1:] if r[7] == "PASS")
    failed = sum(1 for r in rows[1:] if r[7] == "FAIL")
    unav = sum(1 for r in rows[1:] if r[7] == "UNAVAILABLE")
    maxdiff = max((r[6] for r in rows[1:] if r[7] in ("PASS", "FAIL") and r[6] != ""), default=0.0)
    print(f"total={total} passed={passed} failed={failed} unavailable={unav} max_diff={maxdiff:.6f}")


if __name__ == "__main__":
    main()
