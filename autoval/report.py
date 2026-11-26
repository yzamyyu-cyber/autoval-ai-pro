"""Markdown research-report generation from a validated analysis result (no Streamlit)."""
from __future__ import annotations
from .quality import assess_valuation_quality


def _usd(v):
    return f"${v:,.2f}" if v is not None else "n/a"


def _pct(v):
    return f"{v:.1%}" if v is not None else "n/a"


def _growth(s):
    return f"{s['growth']:+.1%}" if s.get("growth") is not None else "Driver-based"


def _num(v):
    return f"{v:,}" if isinstance(v, (int, float)) else "n/a"


def _peer_reason(result: dict) -> str:
    from .peers import peer_groups
    groups = peer_groups(result.get("ticker", ""))
    if not groups:
        return "no peer group configured for this industry"
    return "insufficient valid comparable companies (or data-provider failure)"


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
    demo = result["mode"] == "demo"
    price_label = "Fictional reference price" if demo else "Market close"
    L = []

    L.append(f"# {result['company']} ({result['ticker']}) — Equity Research Report")
    L.append("")
    if demo:
        L.append("> **Synthetic offline example.** The issuer and all figures are fictional. "
                 "This educational report is not investment advice.")
    else:
        L.append("> **Educational prototype — not investment advice.** Prices are delayed. "
                 "Intrinsic value is a model estimate.")
    L.append("")

    L.append("## Company & data dates")
    L.append(f"- {price_label}: **{_usd(a['market_price'])}** as of **{a['price_date']}**")
    L.append(f"- Market-data mode: **{result.get('market_mode', 'current')}**"
             f" · WACC basis: **{result.get('wacc_basis', a.get('wacc_basis', 'n/a'))}**")
    L.append(f"- Financial FY: **{a['financial_asof']}**")
    L.append(f"- Run (UTC): {result['run_utc']}")
    L.append(f"- Shares: common {_num(a.get('shares_outstanding'))} · diluted {_num(a.get('diluted_shares'))}")
    freshness = result.get("freshness") or {}
    if freshness.get("status") == "newer-results-available":
        L.append(f"- ⚠️ Newer results available: earnings release covering "
                 f"{freshness.get('newer_earnings_report_date') or freshness.get('newer_earnings_release')} "
                 f"is later than the latest periodic filing; this valuation uses the periodic filing.")
    L.append("")

    L.append("## Availability")
    L.append(f"- DCF: **{'available' if result.get('analysis') is not None else 'unavailable'}**")
    L.append(f"- Company-specific WACC: **{'available' if (wacc_block or {}).get('available') is True else 'unavailable (illustrative fallback)'}**")
    if relative is not None:
        L.append("- Peer valuation: **available**")
    else:
        L.append(f"- Peer valuation: **unavailable** — {_peer_reason(result)}")
    L.append("")

    quality = assess_valuation_quality(result)
    L.append("## Valuation quality")
    L.append(f"- **State: {quality['state'].replace('_', ' ').upper()}**")
    for r in quality["data_quality"]:
        L.append(f"  - Data quality: {r}")
    for r in quality["unsuitability"]:
        L.append(f"  - Model unsuitable: {r}")
    for r in quality["model_suitability"]:
        L.append(f"  - Model risk: {r}")
    L.append("")

    L.append("## Valuation summary")
    benchmark = "reference" if demo else "market"
    L.append(f"| Scenario | Intrinsic/share | vs {benchmark} | WACC | FCFF growth | Terminal g |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for case in ("bear", "base", "bull"):
        v = cases[case]
        gap = f"{v['upside_vs_price_pct']:+.1f}%" if v.get("upside_vs_price_pct") is not None else "n/a"
        L.append(f"| {case.title()} | {_usd(v['intrinsic_per_share_usd'])} | "
                 f"{gap} | {_pct(v['wacc'])} | {_growth(v)} | {_pct(v['terminal_growth'])} |")
    negative_cases = [c for c in ("bear", "base", "bull")
                      if (cases[c].get("intrinsic_per_share_usd") or 0) < 0]
    if negative_cases:
        L.append("")
        L.append("> ⚠️ A negative intrinsic-per-share figure is a mechanical artifact: that scenario's "
                 "discounted cash flows fall below net debt. Equity is a limited-liability claim and "
                 "cannot have a negative price; the figure is preserved here for audit only and is not "
                 "a valid stock price.")
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

    multistage = a.get("multistage")
    if multistage:
        L.append("## Multi-stage DCF")
        L.append("Years 1–5 explicit · years 6–10 transition · year 11+ ROIC-consistent terminal. "
                 "The original five-year DCF is unchanged.")
        L.append("")
        L.append("| Scenario | Original (5-yr) | Multi-stage |")
        L.append("|---|---:|---:|")
        for case in ("bear", "base", "bull"):
            orig = cases[case]["intrinsic_per_share_usd"]
            ms = multistage[case]["intrinsic_per_share_usd"]
            L.append(f"| {case.title()} | {_usd(orig)} | {_usd(ms)} |")
        L.append("")
        b = multistage["base"]
        L.append(f"- Sustainable reinvestment rate = terminal growth ÷ mature incremental ROIC "
                 f"= {b['terminal_growth']:.1%} ÷ {b['mature_incremental_roic']:.0%} "
                 f"= {b['reinvestment_rate_terminal']:.1%}")
        L.append(f"- Terminal FCFF = year-{b['terminal']['year']} NOPAT × (1 − reinvestment rate) "
                 f"= {_usd(b['terminal']['nopat_usd'])} × (1 − {b['reinvestment_rate_terminal']:.1%}) "
                 f"= {_usd(b['terminal']['fcff_usd'])}")
        L.append(f"- Terminal value = FCFF ÷ (WACC − g) = {_usd(b['terminal']['terminal_value_usd'])}")
        L.append(f"- Explicit reinvestment rate fades from {b['reinvestment_rate_explicit']:.0%} "
                 f"to {b['reinvestment_rate_terminal']:.1%}")
        L.append("- Mature incremental ROIC is an **assumed parameter** (12% default, "
                 "not market-calibrated); transition period is 5 years.")
        L.append("")
        roic_rows = multistage.get("roic_sensitivity") or []
        if roic_rows:
            L.append("| Mature ROIC | Terminal reinvestment | Intrinsic/share |")
            L.append("|---:|---:|---:|")
            for r in roic_rows:
                if r.get("valid"):
                    L.append(f"| {r['mature_incremental_roic']:.0%} | "
                             f"{r['reinvestment_rate_terminal']:.1%} | "
                             f"{_usd(r['intrinsic_per_share_usd'])} |")
            L.append("")

    if relative:
        L.append("## Relative valuation (P/E & EV/EBITDA)")
        t = relative["target"]
        L.append(f"- Target TTM EPS {_usd(t.get('ttm_eps'))} · TTM EBITDA {_usd(t.get('ttm_ebitda'))}")
        for gkey, g in relative["groups"].items():
            pe, ev = g["pe"], g["ev_ebitda"]
            label = g['label'].replace('_', ' ').title()
            pe_n = pe.get("sample_size", 0)
            ev_n = ev.get("sample_size", 0)
            pe_med = f"{pe['median_pe']:.1f}x" if pe['median_pe'] else "n/a"
            ev_med = f"{ev['median_ev_ebitda']:.1f}x" if ev['median_ev_ebitda'] else "n/a"
            L.append(f"- **{label}** — P/E (n={pe_n}): {'median ' + pe_med + ' → implied ' + _usd(pe['implied_price_median']) if pe_n >= 3 else 'insufficient valid peers'}"
                     f" · EV/EBITDA (n={ev_n}): {'median ' + ev_med + ' → implied ' + _usd(ev['implied_price_median']) if ev_n >= 3 else 'insufficient valid peers'}")
    else:
        L.append("## Relative valuation")
        L.append("- Peer estimates are unavailable for this run.")
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
