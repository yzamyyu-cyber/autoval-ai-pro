"""AutoVal AI Pro — Streamlit equity-research website (ticker-only)."""
import os
import json
import streamlit as st
import pandas as pd
from autoval.pipeline import build_analysis
from autoval.report import build_report_markdown

st.set_page_config(page_title="AutoVal AI Pro", page_icon="📈", layout="wide")


def fmt_usd(v):
    return f"${v:,.2f}" if v is not None else "—"


def fmt_b(v):
    return f"${(v or 0)/1e9:,.1f}B" if v is not None else "—"


def fmt_pct(v):
    return f"{v:.1%}" if v is not None else "—"


def scenario_growth(s):
    return fmt_pct(s["growth"]) if s.get("growth") is not None else "Driver-based"


# ------------------------------------------------------------------ state
if "result" not in st.session_state:
    st.session_state.result = None
if "prices" not in st.session_state:
    st.session_state.prices = None
if "ticker" not in st.session_state:
    st.session_state.ticker = None
if "mode" not in st.session_state:
    st.session_state.mode = None

# ------------------------------------------------------------------ brand
st.markdown(
    "<h1 style='margin-bottom:0'>📈 AutoVal AI Pro</h1>"
    "<p style='font-size:1.5rem;font-weight:600;color:#1a1a1a;margin:0'>Understand What a Stock Is Worth</p>"
    "<p style='color:#555;margin-top:0.25rem'>Automated equity research — enter a ticker to receive "
    "a structured, source-linked valuation report.</p>",
    unsafe_allow_html=True,
)
st.caption("U.S. listed non-financial companies · educational prototype · prices may be "
           "delayed (never real-time) · not investment advice")

# ------------------------------------------------------------------ search
mode = st.radio("Data mode", ["Live ticker", "Offline DEMO (synthetic)"], horizontal=True,
                help="Offline DEMO uses a fictional company; never mix with live results.")
if mode == "Live ticker":
    ticker = st.text_input("Stock ticker", "MSFT", max_chars=10,
                           placeholder="e.g. MSFT, HD",
                           help="U.S. ticker symbol, 1–10 letters/numbers").strip().upper()
else:
    ticker = "DEMO"
    st.info("DEMO is entirely synthetic and does not correspond to a traded stock.")

analyze = st.button("🔍 Analyze Stock", type="primary", use_container_width=True)

if analyze:
    if not ticker:
        st.error("Please enter a ticker.")
    elif not ticker.isalnum():
        st.error("Ticker must be 1–10 letters/numbers (e.g. MSFT).")
    else:
        with st.spinner("Retrieving SEC filings and market data, computing valuation…"):
            try:
                result, prices = build_analysis(
                    ticker, "demo" if mode.startswith("Offline") else "live",
                    os.environ.get("SEC_USER_AGENT", ""))
                st.session_state.result = result
                st.session_state.prices = prices
                st.session_state.ticker = ticker
                st.session_state.mode = "demo" if mode.startswith("Offline") else "live"
            except Exception as exc:
                st.error(f"Analysis stopped: {exc}")
                st.info("Live mode needs a SEC_USER_AGENT contact identifier. Missing tags, "
                        "stale data or provider limits stop the run rather than inventing figures.")

result = st.session_state.result
prices = st.session_state.prices
if (result is not None and result.get("ticker") == ticker
        and result.get("mode") == st.session_state.mode):
    analysis = result["analysis"]
    cases = analysis["scenarios"]
    bridge = analysis.get("bridge")
    forecast = analysis.get("forecast")
    wacc_block = result.get("wacc")
    relative = result.get("relative")
    live = result["mode"] == "live"
    price = analysis["market_price"]

    # ------------------------------ 1. header ------------------------------
    st.divider()
    st.markdown(f"## {result['company']} ({result['ticker']})")
    st.caption(f"Market close **{fmt_usd(price)}** (price date **{analysis['price_date']}**, delayed) · "
               f"Financial FY **{analysis['financial_asof']}** · Analysis run **{result['run_utc'][:19].replace('T', ' ')} UTC**")
    if st.button("🔄 Analyze Another Stock"):
        for k in ("result", "prices", "ticker", "mode"):
            st.session_state[k] = None
        st.rerun()

    # ------------------------------ 2. executive summary ------------------------------
    st.subheader("Executive valuation summary")
    base = cases["base"]["intrinsic_per_share_usd"]
    s1, s2, s3 = st.columns(3)
    s1.metric("Market close", fmt_usd(price))
    s2.metric("Base intrinsic / share", fmt_usd(base),
              f"{cases['base']['upside_vs_price_pct']:+.1f}% vs market")
    s3.metric("Company WACC", fmt_pct((wacc_block or {}).get("wacc")),
              "estimated" if live else "illustrative")
    st.caption("Intrinsic value is the DCF estimate; the market price is a delayed close. "
               "A large gap reflects the model's conservative assumptions — it is not a "
               "buy/sell signal.")

    # ------------------------------ 3. Bear / Base / Bull ------------------------------
    with st.expander("Bear / Base / Bull DCF estimates", expanded=True):
        rows = []
        for case in ("bear", "base", "bull"):
            v = cases[case]
            rows.append({"Scenario": case.title(),
                         "Intrinsic / share": fmt_usd(v["intrinsic_per_share_usd"]),
                         "vs market": f"{v['upside_vs_price_pct']:+.1f}%",
                         "WACC": fmt_pct(v["wacc"]),
                         "FCFF growth": scenario_growth(v),
                         "Terminal g": fmt_pct(v["terminal_growth"])})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("**Bear / Base / Bull** differ by revenue-growth, margin and reinvestment "
                   "assumptions; one WACC is applied to all three.")

    # ------------------------------ 4. intrinsic vs market ------------------------------
    with st.expander("Intrinsic value vs market price"):
        chart = pd.DataFrame({
            "USD / share": [cases[k]["intrinsic_per_share_usd"] for k in ("bear", "base", "bull")] + [price],
        }, index=["Bear", "Base", "Bull", "Market close"])
        st.bar_chart(chart)
        if bridge:
            elig = bridge["eligible_nonoperating_securities_usd"]
            note = (f"Investment-adjusted Base: conservative "
                    f"{fmt_usd(cases['base'].get('intrinsic_per_share_usd_conservative'))} · "
                    f"upper {fmt_usd(cases['base'].get('intrinsic_per_share_usd_upper'))}")
            if "reconciled" in elig:
                note += f" · reconciled {fmt_usd(cases['base'].get('intrinsic_per_share_usd_reconciled'))}"
            st.caption(note)

    # ------------------------------ 5. forecast ------------------------------
    if forecast:
        with st.expander("Five-year financial forecast"):
            st.caption("**Driver-based**: `FCFF = NOPAT + D&A − CapEx − ΔNWC`.")
            d = forecast["base"]["drivers"]
            st.markdown(
                f"Revenue growth **{fmt_pct(d['revenue_growth'])}** · operating margin "
                f"**{fmt_pct(d['operating_margin'])}** · tax **{fmt_pct(d['normalized_tax_rate'])}** · "
                f"D&A **{fmt_pct(d['da_ratio'])}** · CapEx **{fmt_pct(d['capex_ratio'])}** of revenue")
            frow = [{"Year": r["year"], "Revenue": fmt_b(r["revenue"]), "EBIT": fmt_b(r["ebit"]),
                     "NOPAT": fmt_b(r["nopat"]), "D&A": fmt_b(r["da"]), "CapEx": fmt_b(r["capex"]),
                     "ΔNWC": fmt_b(r["change_in_nwc"]), "FCFF": fmt_b(r["fcff"])}
                    for r in forecast["base"]["rows"]]
            st.dataframe(pd.DataFrame(frow), use_container_width=True, hide_index=True)

    # ------------------------------ 6. comparable companies ------------------------------
    with st.expander("Comparable-company valuation (P/E & EV/EBITDA)"):
        if not relative:
            st.info("No peer group is configured for this ticker, so relative valuation is "
                    "unavailable — disclosed rather than fabricated.")
        else:
            t = relative["target"]
            st.caption(f"Target TTM EPS **{fmt_usd(t.get('ttm_eps'))}** · TTM EBITDA "
                       f"**{fmt_b(t.get('ttm_ebitda'))}**")
            for gkey, g in relative["groups"].items():
                label = g['label'].replace('_',' ').title()
                nnote = " — single observation, not a meaningful median" if g['sample_size'] < 3 else ""
                st.markdown(f"**{label}** (n={g['sample_size']}){nnote}")
                prow = [{"Peer": p["ticker"],
                         "P/E": f"{p['pe']:.1f}x" if p.get("pe") else "—",
                         "EV/EBITDA": f"{p['ev_ebitda']:.1f}x" if p.get("ev_ebitda") else "—",
                         "Mkt cap": fmt_b(p.get("market_cap"))} for p in g["peers"]]
                st.dataframe(pd.DataFrame(prow), use_container_width=True, hide_index=True)
                if g['sample_size'] >= 3:
                    pe, ev = g["pe"], g["ev_ebitda"]
                    pe_med = f"{pe['median_pe']:.1f}x" if pe['median_pe'] else "—"
                    ev_med = f"{ev['median_ev_ebitda']:.1f}x" if ev['median_ev_ebitda'] else "—"
                    st.caption(
                        f"Median P/E **{pe_med}** → implied {fmt_usd(pe['implied_price_median'])} · "
                        f"Median EV/EBITDA **{ev_med}** → implied {fmt_usd(ev['implied_price_median'])}")

    # ------------------------------ 7. WACC & sensitivity ------------------------------
    with st.expander("Company-specific WACC & sensitivity"):
        if not wacc_block or not wacc_block.get("available"):
            st.warning("Company-specific WACC unavailable — intrinsic values use the "
                       "illustrative (non-company-specific) WACC and are labeled accordingly.")
        else:
            c = wacc_block["calculation"]
            st.markdown(f"**WACC = {fmt_pct(c['wacc'])}** — cost of equity {fmt_pct(c['cost_of_equity'])}, "
                        f"after-tax cost of debt {fmt_pct(c['after_tax_cost_of_debt'])}, "
                        f"equity weight {fmt_pct(c['equity_weight'])}.")
            st.caption(f"rf {fmt_pct(c['risk_free_rate'])} · β {c['beta']:.2f} · ERP "
                       f"{fmt_pct(c['equity_risk_premium'])} · marginal tax {fmt_pct(c['marginal_tax_rate'])}")
        sens = analysis.get("sensitivity")
        if sens:
            st.markdown("**WACC × terminal growth → intrinsic / share (USD)**")
            sdf = pd.DataFrame(sens).pivot(index="terminal_growth", columns="wacc",
                                           values="intrinsic_per_share_usd")
            sdf = sdf.sort_index().sort_index(axis=1)  # numeric ascending
            sdf = sdf.map(lambda v: f"${v:,.2f}" if pd.notna(v) else "—")
            sdf.index = [f"{g:.1%}" for g in sdf.index]
            sdf.columns = [f"{w:.2%}" for w in sdf.columns]
            st.dataframe(sdf, use_container_width=True)
        cs = analysis.get("capex_sensitivity")
        if cs:
            st.caption(f"CapEx sensitivity: base **{cs['capex_ratio_cases']['three_year_mean']:.1%}** → "
                       f"{fmt_usd(cases['base']['intrinsic_per_share_usd'])} · persistent high "
                       f"**{cs['high_capex_ratio']:.1%}** → {fmt_usd(cs['intrinsic_per_share_usd']['base'])}")

    # ------------------------------ 8. technical ------------------------------
    with st.expander("Technical analysis & backtest"):
        if prices is not None:
            st.line_chart(prices[["close", "sma20", "sma50", "sma200"]], height=300)
        t = result["technical"]
        st.markdown(f"SMA20 **{t['sma20']:,.2f}** · SMA50 **{t['sma50']:,.2f}** · SMA200 "
                    f"**{t['sma200']:,.2f}** · trend **{t['trend']}**")
        c1, c2 = st.columns(2)
        c1.metric("Strategy return", f"{t['strategy_total_return_pct']:+.2f}%")
        c2.metric("Buy-and-hold", f"{t['buyhold_total_return_pct']:+.2f}%")
        st.caption(t["warning"])

    # ------------------------------ 9. sources ------------------------------
    with st.expander("Sources, assumptions & data-quality"):
        prov = result["provenance"]
        fin = prov["financials"]
        st.markdown(f"- **Financial source:** {fin['provider']}" +
                    (f" (CIK {fin.get('cik')})" if fin.get("cik") else ""))
        st.markdown(f"- **Market source:** {prov['market']['provider']} · realtime={prov['market'].get('realtime')}")
        ap = analysis["assumption_provenance"]
        st.markdown(f"- **WACC:** {ap['wacc']}  · **Terminal growth:** {ap['terminal_growth']}")
        for lim in result.get("limitations", []):
            st.caption(f"• {lim}")

    # ------------------------------ 10. verification ------------------------------
    with st.expander("Independent verification & reproducibility"):
        st.markdown(
            "- `verify_output.py` recomputes the DCF with `Decimal` arithmetic to <$0.01/share.\n"
            "- Automated test suite (`unittest discover -s tests`) covers finance, SEC, "
            "forecast, WACC, relative-valuation and report logic.\n"
            "- Every assumption carries its source, date and classification; missing inputs "
            "are disclosed, never silently substituted.")
        st.download_button("⬇️ Download research report (Markdown)",
                           data=build_report_markdown(result),
                           file_name=f"autoval_{result['ticker'].lower()}_report.md",
                           mime="text/markdown")
        st.download_button("Download analysis JSON", data=json.dumps(result, indent=2),
                           file_name=f"autoval_{result['ticker'].lower()}.json", mime="application/json")

    st.caption("Educational research prototype — **not** investment advice; no buy/sell recommendation is implied.")
else:
    st.info("Enter a ticker and click **Analyze**. For a guaranteed offline example, choose **Offline DEMO**.")
