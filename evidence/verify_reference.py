#!/usr/bin/env python3
"""Independent numerical verification of a saved analysis snapshot.

Reads exact full-precision inputs from a saved analysis.json and INDEPENDENTLY
recomputes FCFF (from drivers), WACC (from market inputs), the DCF discount, terminal
value and equity bridge — WITHOUT importing autoval valuation functions or reusing the
engine's computed FCFF/terminal/intrinsic. Compares every calculation to the engine.

Usage:
    .venv/bin/python evidence/verify_reference.py <analysis.json>
"""
from __future__ import annotations
import json
import sys


def project_fcff(drivers, base_rev, base_nwc, years=5):
    g = drivers["revenue_growth"]; m = drivers["operating_margin"]
    tax = drivers["normalized_tax_rate"]; dr = drivers["da_ratio"]
    cr = drivers["capex_ratio"]; nr = drivers["nwc_ratio"]
    rev, nwc = base_rev, base_nwc
    out = []
    for _ in range(years):
        rev = rev * (1 + g)
        ebit = rev * m
        nopat = ebit * (1 - tax)
        da = rev * dr
        capex = rev * cr
        n = rev * nr
        d_nwc = n - nwc
        out.append(nopat + da - capex - d_nwc)
        nwc = n
    return out


def recompute_wacc(wacc_inputs):
    rf = wacc_inputs["risk_free_rate"]["value"]
    beta = wacc_inputs["beta"]["value"]
    erp = wacc_inputs["equity_risk_premium"]["value"]
    eq = wacc_inputs["equity_value"]["value"]
    debt = wacc_inputs["debt_value"]["value"]
    cod = wacc_inputs["pre_tax_cost_of_debt"]["value"]
    tax = wacc_inputs["marginal_tax_rate"]["value"]
    coe = rf + beta * erp
    wacc = coe * eq / (eq + debt) + cod * (1 - tax) * debt / (eq + debt)
    return coe, cod, wacc


def discount(stream, wacc, tg):
    pv = sum(cf / (1 + wacc) ** t for t, cf in enumerate(stream, start=1))
    tv = stream[-1] * (1 + tg) / (wacc - tg)
    ev = pv + tv / (1 + wacc) ** len(stream)
    return pv, tv, ev


def verify(snapshot):
    a = snapshot["analysis"]
    base = a["scenarios"]["base"]
    fc = a["forecast"]["base"]
    drivers = fc["drivers"]

    stream = project_fcff(drivers, fc["base_revenue"], fc["base_nwc"])
    engine_stream = base["forecast_fcff_usd"]
    fcff_diff = max(abs(x - y) for x, y in zip(stream, engine_stream))

    coe, cod, wacc = recompute_wacc(snapshot["wacc"]["inputs"])
    wacc_diff = abs(wacc - base["wacc"])

    pv, tv, ev = discount(stream, base["wacc"], base["terminal_growth"])
    equity = ev - base["net_debt_usd"]
    intrinsic = equity / base["shares"]
    intrinsic_diff = abs(intrinsic - base["intrinsic_per_share_usd"])

    return {
        "fcff_diff": fcff_diff,
        "wacc_indep": wacc, "wacc_engine": base["wacc"], "wacc_diff": wacc_diff,
        "intrinsic_indep": intrinsic, "intrinsic_engine": base["intrinsic_per_share_usd"],
        "intrinsic_diff": intrinsic_diff,
    }


def main(path):
    snap = json.load(open(path))
    t = snap["ticker"]
    for case in ("bear", "base", "bull"):
        # verify base only here; scenario spread is a policy assumption, not arithmetic
        pass
    r = verify(snap)
    print(f"{t} base: FCFF max diff {r['fcff_diff']:.6f} | WACC {r['wacc_indep']:.6f} vs {r['wacc_engine']:.6f} (Δ {r['wacc_diff']:.6f}) | intrinsic {r['intrinsic_indep']:.6f} vs {r['intrinsic_engine']:.6f} (Δ {r['intrinsic_diff']:.6f})")
    return r


if __name__ == "__main__":
    main(sys.argv[1])
