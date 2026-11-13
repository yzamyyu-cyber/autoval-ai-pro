"""Markdown research-report generation from a validated analysis result (no Streamlit)."""
from __future__ import annotations


def _usd(v):
    return f"${v:,.2f}" if v is not None else "n/a"


def _pct(v):
    return f"{v:.1%}" if v is not None else "n/a"


def _growth(s):
    return f"{s['growth']:+.1%}" if s.get("growth") is not None else "Driver-based"


def _num(v):
    return f"{v:,}" if isinstance(v, (int, float)) else "n/a"


def build_report_markdown(result: dict) -> str:
    """Render a Markdown equity-research report from `build_analysis()` output.

    Uses only validated program data; every optional block is guarded so missing
    peer/WACC/forecast data is disclosed rather than erroring.
    """
    a = result["analysis"]
    cases = a["scenarios"]
    bridge = a.get("bridge")
    forecast = a.get("forecast")
    wacc_block = result.get("wacc")
    relative = result.get("relative")
    ap = a["assumption_provenance"]
    L = []

    L.append(f"# {result['company']} ({result['ticker']}) — Equity Research Report")
    L.append("")
    L.append("> **Educational prototype — not investment advice.** Prices are delayed (never "
             "real-time). Intrinsic value is a model estimate, not a buy/sell signal.")
    L.append("")

    L.append("## Company & data dates")
    L.append(f"- Market close: **{_usd(a['market_price'])}** as of **{a['price_date']}**")
    L.append(f"- Financial FY: **{a['financial_asof']}**")
    L.append(f"- Run (UTC): {result['run_utc']}")
    L.append(f"- Shares: common {_num(a.get('shares_outstanding'))} · diluted {_num(a.get('diluted_shares'))}")
    L.append("")

    L.append("## Valuation summary")
    L.append("| Scenario | Intrinsic/share | vs market | WACC | FCFF growth | Terminal g |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for case in ("bear", "base", "bull"):
        v = cases[case]
        L.append(f"| {case.title()} | {_usd(v['intrinsic_per_share_usd'])} | "
                 f"{v['upside_vs_price_pct']:+.1f}% | {_pct(v['wacc'])} | {_growth(v)} | {_pct(v['terminal_growth'])} |")
    L.append("")

    L.append("## Assumptions")
    L.append(f"- Growth: {ap.get('growth') or ap.get('method') or 'n/a'}")
    L.append(f"- WACC: {ap['wacc']}")
    L.append(f"- Terminal growth: {ap['terminal_growth']}")
    if forecast:
        d = forecast["base"]["drivers"]
        L.append(f"- Revenue growth {_pct(d['revenue_growth'])} · operating margin "
                 f"{_pct(d['operating_margin'])} · tax {_pct(d['normalized_tax_rate'])} · "
                 f"D&A {_pct(d['da_ratio'])} · CapEx {_pct(d['capex_ratio'])} of revenue")
    L.append("")

    L.append("## DCF (Base case)")
    base = cases["base"]
    L.append(f"- Enterprise value: {_usd(base['enterprise_value_usd'])}")
    L.append(f"- Net debt: {_usd(base['net_debt_usd'])}")
    L.append(f"- Equity value: {_usd(base['equity_value_usd'])}")
    L.append(f"- Intrinsic/share: {_usd(base['intrinsic_per_share_usd'])}")
    L.append(f"- Terminal value weight of EV: {base['terminal_weight_of_ev']:.1%}")
    if bridge:
        elig = bridge["eligible_nonoperating_securities_usd"]
        L.append(f"- Investment-adjusted: conservative {_usd(cases['base'].get('intrinsic_per_share_usd_conservative'))}, "
                 f"upper {_usd(cases['base'].get('intrinsic_per_share_usd_upper'))}"
                 + (f", reconciled {_usd(cases['base'].get('intrinsic_per_share_usd_reconciled'))}"
                    if "reconciled" in elig else ""))
    L.append("")

    L.append("## Company-specific WACC")
    if wacc_block and wacc_block.get("available"):
        c = wacc_block["calculation"]
        L.append(f"- **WACC = {_pct(c['wacc'])}** (cost of equity {_pct(c['cost_of_equity'])}, "
                 f"after-tax cost of debt {_pct(c['after_tax_cost_of_debt'])})")
        L.append(f"- Risk-free {_pct(c['risk_free_rate'])} · beta {c['beta']:.2f} · ERP "
                 f"{_pct(c['equity_risk_premium'])} · marginal tax {_pct(c['marginal_tax_rate'])}")
    else:
        L.append("- Company-specific WACC unavailable; intrinsic values use the illustrative "
                 "(non-company-specific) WACC and are labeled accordingly.")
    L.append("")

    sens = a.get("sensitivity")
    if sens:
        L.append("## Sensitivity (WACC × terminal growth → intrinsic/share)")
        sdf = {}
        waccs = sorted(set(round(r["wacc"], 4) for r in sens))
        tgs = sorted(set(round(r["terminal_growth"], 4) for r in sens))
        L.append("| Terminal g \\ WACC | " + " | ".join(f"{w:.2%}" for w in waccs) + " |")
        L.append("|---" * (len(waccs) + 1) + "|")
        for tg in tgs:
            vals = []
            for w in waccs:
                hit = next((r for r in sens if round(r["wacc"], 4) == w and round(r["terminal_growth"], 4) == tg), None)
                vals.append(f"{hit['intrinsic_per_share_usd']:.0f}" if hit else "—")
            L.append(f"| {tg:.1%} | " + " | ".join(vals) + " |")
        L.append("")
    cs = a.get("capex_sensitivity")
    if cs:
        L.append("## CapEx sensitivity")
        L.append(f"- Base CapEx intensity {cs['capex_ratio_cases']['three_year_mean']:.1%} → "
                 f"Base intrinsic {_usd(cases['base']['intrinsic_per_share_usd'])}")
        L.append(f"- Persistent high CapEx {cs['high_capex_ratio']:.1%} → "
                 f"Base intrinsic {_usd(cs['intrinsic_per_share_usd']['base'])}")
        L.append("")

    if forecast:
        L.append("## Five-year forecast (Base, USD B)")
        L.append("| Year | Revenue | EBIT | NOPAT | D&A | CapEx | ΔNWC | FCFF |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in forecast["base"]["rows"]:
            L.append(f"| {r['year']} | {r['revenue']/1e9:.2f} | {r['ebit']/1e9:.2f} | "
                     f"{r['nopat']/1e9:.2f} | {r['da']/1e9:.2f} | {r['capex']/1e9:.2f} | "
                     f"{r['change_in_nwc']/1e9:.2f} | {r['fcff']/1e9:.2f} |")
        L.append("")

    if relative:
        L.append("## Relative valuation (P/E & EV/EBITDA)")
        t = relative["target"]
        L.append(f"- Target TTM EPS {_usd(t.get('ttm_eps'))} · TTM EBITDA {_usd(t.get('ttm_ebitda'))}")
        for gkey, g in relative["groups"].items():
            pe, ev = g["pe"], g["ev_ebitda"]
            label = g['label'].replace('_', ' ').title()
            if g['sample_size'] < 3:
                L.append(f"- **{label}** (n={g['sample_size']}): single/limited observation — "
                         f"not a statistically meaningful median")
            else:
                pe_med = f"{pe['median_pe']:.1f}x" if pe['median_pe'] else "n/a"
                ev_med = f"{ev['median_ev_ebitda']:.1f}x" if ev['median_ev_ebitda'] else "n/a"
                L.append(f"- **{label}** (n={g['sample_size']}): median P/E {pe_med} → implied "
                         f"{_usd(pe['implied_price_median'])}; median EV/EBITDA {ev_med} → implied "
                         f"{_usd(ev['implied_price_median'])}")
    else:
        L.append("## Relative valuation")
        L.append("- Not available (no peer group configured for this ticker).")
    L.append("")

    L.append("## Sources & limitations")
    prov = result["provenance"]
    L.append(f"- Financial source: {prov['financials']['provider']}")
    L.append(f"- Market source: {prov['market']['provider']}")
    for lim in result.get("limitations", []):
        L.append(f"- {lim}")
    L.append("")
    L.append("---")
    L.append("Generated by AutoVal AI Pro from validated program data. This is an educational "
             "prototype and does not constitute investment advice.")
    return "\n".join(L)
