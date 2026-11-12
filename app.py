"""Streamlit equity-research dashboard — ticker-only AutoVal AI Pro."""
import os
import json
import streamlit as st
import pandas as pd
from autoval.pipeline import build_analysis

st.set_page_config(page_title="AutoVal AI Pro", page_icon="📈", layout="wide")


def fmt_usd(v):
    return f"${v:,.2f}"


def fmt_b(v):
    return f"${(v or 0) / 1e9:,.1f}B"


def scenario_intrinsic(s, variant):
    """Return a scenario's intrinsic value for a given bridge variant, falling back
    to the cash-only value when the variant is absent (e.g. no reconciled case)."""
    key = "intrinsic_per_share_usd" if variant == "cash_only" else f"intrinsic_per_share_usd_{variant}"
    return s.get(key, s.get("intrinsic_per_share_usd"))


st.title("📈 AutoVal AI Pro")
st.caption("Enter a ticker → SEC filings + latest available market close → transparent DCF valuation + technical backtest")
st.warning("Research prototype. Prices may be delayed and are never real-time. DCF assumptions are illustrative, not calibrated. Not trading advice.")

mode = st.radio("Data mode", ["Live ticker", "Offline DEMO (synthetic)"], horizontal=True,
                help="Offline DEMO uses a fictional company and synthetic prices; never mix with live figures.")
if mode == "Live ticker":
    ticker = st.text_input("Stock ticker", "MSFT", max_chars=10).strip().upper()
else:
    ticker = "DEMO"
    st.info("DEMO is entirely synthetic and does not correspond to a traded stock.")

if st.button("Analyze", type="primary"):
    if not ticker:
        st.error("Please enter a ticker.")
        st.stop()
    if not ticker.isalnum():
        st.error("Ticker must be 1–10 letters/numbers (e.g. MSFT).")
        st.stop()
    with st.spinner("Retrieving SEC data and market prices, validating financials and calculating..."):
        try:
            result, prices = build_analysis(ticker, "demo" if mode.startswith("Offline") else "live",
                                            os.environ.get("SEC_USER_AGENT", ""))
            st.session_state["results"] = result
            st.session_state["prices"] = prices
        except Exception as exc:
            st.error(f"Analysis stopped: {exc}")
            st.info("SEC live mode requires a SEC_USER_AGENT contact identifier. Missing accounting tags, stale data, or provider limits stop valuation rather than producing invented numbers.")
            st.stop()

res = st.session_state.get("results")
if (res is not None and res.get("ticker") == ticker
        and res.get("mode") == ("demo" if mode.startswith("Offline") else "live")):
    result = res
    prices = st.session_state["prices"]
    analysis = result["analysis"]
    cases = analysis["scenarios"]
    bridge = analysis.get("bridge")
    has_bridge = bridge is not None

    st.subheader(f"{result['company']} — {result['ticker']}")
    st.caption(f"Market close as of **{analysis['price_date']}** (delayed, not real-time) · "
               f"Financial FY **{analysis['financial_asof']}** · Run UTC **{result['run_utc']}**")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest available close", fmt_usd(analysis["market_price"]),
              help="Delayed closing price; not real-time.")
    c2.metric("Bear (cash-only)", fmt_usd(cases["bear"]["intrinsic_per_share_usd"]),
              f"{cases['bear']['upside_vs_price_pct']:+.1f}% vs close")
    c3.metric("Base (cash-only)", fmt_usd(cases["base"]["intrinsic_per_share_usd"]),
              f"{cases['base']['upside_vs_price_pct']:+.1f}% vs close")
    c4.metric("Bull (cash-only)", fmt_usd(cases["bull"]["intrinsic_per_share_usd"]),
              f"{cases['bull']['upside_vs_price_pct']:+.1f}% vs close")

    tab_v, tab_f, tab_r, tab_w, tab_t, tab_s = st.tabs(["Valuation", "Forecast", "Relative valuation", "WACC", "Technical analysis", "Sources, assumptions & data quality"])

    with tab_v:
        st.markdown("#### DCF scenarios vs market price")
        chart = pd.DataFrame({
            "USD / share": [cases[k]["intrinsic_per_share_usd"] for k in ("bear", "base", "bull")]
                           + [analysis["market_price"]],
        }, index=["Bear", "Base", "Bull", "Market close"])
        st.bar_chart(chart)

        st.markdown("#### Scenario table (cash-only bridge)")
        rows = []
        for case, v in cases.items():
            rows.append({
                "Case": case.title(),
                "Intrinsic/share (cash-only)": round(v["intrinsic_per_share_usd"], 2),
                "Upside vs close": f"{v['upside_vs_price_pct']:+.1f}%",
                "WACC": f"{v['wacc']:.1%}",
                "FCFF growth": f"{v['growth']:+.1%}",
                "Terminal g": f"{v['terminal_growth']:.1%}",
                "Terminal weight %": round(v["terminal_weight_of_ev"] * 100, 1),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if has_bridge:
            st.markdown("#### Enterprise-to-equity bridge (investment-adjusted)")
            comp_rows = pd.DataFrame([
                {"Component": "Operating enterprise value (base)", "Amount (USD)": fmt_b(bridge["operating_enterprise_value_usd"])},
                {"Component": "Total interest-bearing debt", "Amount (USD)": fmt_b(bridge["total_debt_usd"])},
                {"Component": "Cash & cash equivalents", "Amount (USD)": fmt_b(bridge["cash_and_equivalents_usd"])},
                {"Component": "Short-term investments", "Amount (USD)": fmt_b(bridge["short_term_investments_usd"])},
                {"Component": "Restricted investments (total)", "Amount (USD)": fmt_b(bridge["restricted_investments_total_usd"])},
                {"Component": "Long-term / equity investments (excluded)", "Amount (USD)": fmt_b(bridge["long_term_investments_usd"])},
            ])
            st.dataframe(comp_rows, use_container_width=True, hide_index=True)

            st.markdown("**Eligible nonoperating securities (range)**")
            elig = bridge["eligible_nonoperating_securities_usd"]
            e1, e2, e3 = st.columns(3)
            e1.metric("Conservative", fmt_b(elig["conservative"]),
                      help="Short-term investments minus ALL restricted investments (may over-subtract).")
            e2.metric("Upper bound", fmt_b(elig["upper"]),
                      help="Full short-term investments — assumes all qualify; NOT a verified value.")
            if "reconciled" in elig:
                e3.metric("Reconciled", fmt_b(elig["reconciled"]),
                          help="Short-term investments minus note-verified restricted-in-short-term.")
            else:
                e3.metric("Reconciled", "Not verified",
                          help="Restricted-in-short-term allocation is note-only and not auto-verified.")

            st.markdown("**Intrinsic value per share — cash-only vs investment-adjusted**")
            iv = {"Scenario": [], "Cash-only": [], "Conservative": [], "Upper": []}
            has_reconciled = "reconciled" in elig
            if has_reconciled:
                iv["Reconciled"] = []
            for case in ("bear", "base", "bull"):
                s = cases[case]
                iv["Scenario"].append(case.title())
                iv["Cash-only"].append(round(scenario_intrinsic(s, "cash_only"), 2))
                iv["Conservative"].append(round(scenario_intrinsic(s, "conservative"), 2))
                iv["Upper"].append(round(scenario_intrinsic(s, "upper"), 2))
                if has_reconciled:
                    iv["Reconciled"].append(round(scenario_intrinsic(s, "reconciled"), 2))
            st.dataframe(pd.DataFrame(iv), use_container_width=True, hide_index=True)

            for n in bridge.get("notes", []):
                st.caption(f"• {n}")
        else:
            st.info("No investment-adjusted bridge for this run (DEMO is synthetic; cash-only bridge shown).")

        st.markdown("#### Observed multiples (not independent fair-value estimates)")
        m1, m2 = st.columns(2)
        m1.metric("Market P/E", f"{result['multiples']['price_to_earnings']:.2f}x"
                  if result['multiples']['price_to_earnings'] else "Unavailable")
        m2.metric("Market EV/EBITDA", f"{result['multiples']['ev_to_ebitda']:.2f}x"
                  if result['multiples']['ev_to_ebitda'] else "Unavailable")

    with tab_f:
        forecast = analysis.get("forecast")
        history = result.get("forecast_history")
        if not forecast:
            st.info("No driver-based forecast for this run (constant-growth fallback or synthetic DEMO).")
        else:
            st.markdown("#### Historical vs forecast revenue")
            chart_rows = []
            for y, r in zip(history.get("fiscal_years", []), history.get("revenue", [])):
                chart_rows.append({"Year": y, "Revenue (M)": r / 1e6, "Series": "Historical"})
            for case in ("bear", "base", "bull"):
                for r in forecast[case]["rows"]:
                    chart_rows.append({"Year": f"FY+{r['year']}", "Revenue (M)": r["revenue"] / 1e6, "Series": case.title()})
            cdf = pd.DataFrame(chart_rows).pivot(index="Year", columns="Series", values="Revenue (M)")
            st.line_chart(cdf)

            st.markdown("#### Bear / Base / Bull driver assumptions (derived from trailing 3-year history)")
            drow = []
            for case in ("bear", "base", "bull"):
                d = forecast[case]["drivers"]
                drow.append({
                    "Scenario": case.title(),
                    "Revenue growth": f"{d['revenue_growth']:.1%}",
                    "Operating margin": f"{d['operating_margin']:.1%}",
                    "Normalized tax": f"{d['normalized_tax_rate']:.1%}",
                    "D&A % rev": f"{d['da_ratio']:.1%}",
                    "CapEx % rev": f"{d['capex_ratio']:.1%}",
                    "NWC % rev": f"{d['nwc_ratio']:.1%}",
                })
            st.dataframe(pd.DataFrame(drow), use_container_width=True, hide_index=True)

            st.markdown("#### Five-year FCFF projections (USD M)")
            frow = []
            for case in ("bear", "base", "bull"):
                for r in forecast[case]["rows"]:
                    frow.append({
                        "Scenario": case.title(), "Year": r["year"],
                        "Revenue": round(r["revenue"] / 1e6),
                        "EBIT": round(r["ebit"] / 1e6),
                        "NOPAT": round(r["nopat"] / 1e6),
                        "D&A": round(r["da"] / 1e6),
                        "CapEx": round(r["capex"] / 1e6),
                        "ΔNWC": round(r["change_in_nwc"] / 1e6),
                        "FCFF": round(r["fcff"] / 1e6),
                    })
            st.dataframe(pd.DataFrame(frow), use_container_width=True, hide_index=True)

            st.markdown("#### Driver-based DCF valuation")
            vrow = []
            for case in ("bear", "base", "bull"):
                s = analysis["scenarios"][case]
                vrow.append({
                    "Scenario": case.title(),
                    "Intrinsic/share": round(s["intrinsic_per_share_usd"], 2),
                    "Upside vs close": f"{s['upside_vs_price_pct']:+.1f}%",
                    "WACC": f"{s['wacc']:.1%}",
                    "Terminal g": f"{s['terminal_growth']:.1%}",
                })
            st.dataframe(pd.DataFrame(vrow), use_container_width=True, hide_index=True)

            cs = analysis.get("capex_sensitivity")
            if cs:
                st.markdown("#### CapEx-intensity sensitivity (persistent-high-investment)")
                rcs = cs["capex_ratio_cases"]
                st.caption(f"CapEx / revenue: 3-yr mean **{rcs['three_year_mean']:.1%}** (base) · "
                           f"FY2026 **{rcs['fy_latest']:.1%}** · 6-yr mean **{rcs['six_year_mean']:.1%}** · "
                           f"6-yr median **{rcs['six_year_median']:.1%}**")
                crow = []
                for case in ("bear", "base", "bull"):
                    base_v = analysis["scenarios"][case]["intrinsic_per_share_usd"]
                    high_v = cs["intrinsic_per_share_usd"][case]
                    crow.append({"Scenario": case.title(),
                                 "Intrinsic (base capex)": round(base_v, 2),
                                 "Intrinsic (34.9% capex)": round(high_v, 2),
                                 "Δ": f"{high_v - base_v:+.2f}"})
                st.dataframe(pd.DataFrame(crow), use_container_width=True, hide_index=True)
                st.caption(f"⚠️ {cs['label']}")

            st.markdown("#### Data sources & limitations")
            for lim in (history.get("limitations") or []):
                st.caption(f"⚠️ {lim}")
            for w in (history.get("warnings") or []):
                st.caption(f"⚠️ {w}")
            st.caption("Driver assumptions are derived from trailing 3-year historical ratios/trends "
                       "(revenue CAGR, operating margin, D&A/CapEx % of revenue) plus a documented 21% "
                       "normalized tax rate — not forward guidance. NWC uses the latest balance sheet.")

    with tab_r:
        relative = result.get("relative")
        if not relative:
            st.info("Relative valuation is available for live tickers with configured peers.")
        else:
            target = relative["target"]
            st.markdown(f"#### Target — {result['company']} ({result['ticker']})")
            st.caption(f"TTM EPS ${target.get('ttm_eps') or 0:.2f} · "
                       f"TTM EBITDA ${(target.get('ttm_ebitda') or 0)/1e9:,.1f}B · "
                       f"Market cap ${(target.get('market_cap') or 0)/1e9:,.0f}B · "
                       f"Price {target.get('price_date')} (delayed, not real-time)")
            for gkey, g in relative["groups"].items():
                label = g["label"].replace("_", " ").title()
                st.markdown(f"**{label}** (n={g['sample_size']})")
                prow = []
                for p in g["peers"]:
                    prow.append({
                        "Peer": p["ticker"],
                        "P/E": round(p["pe"], 1) if p.get("pe") else "—",
                        "EV/EBITDA": round(p["ev_ebitda"], 1) if p.get("ev_ebitda") else "—",
                        "Mkt cap ($B)": round(p["market_cap"]/1e9) if p.get("market_cap") else "—",
                        "Price date": p.get("price_date"),
                    })
                st.dataframe(pd.DataFrame(prow), use_container_width=True, hide_index=True)
                pe = g["pe"]; ev = g["ev_ebitda"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Median P/E", f"{pe['median_pe']:.1f}x" if pe['median_pe'] else "—")
                c2.metric("P25 P/E", f"{pe['p25_pe']:.1f}x" if pe['p25_pe'] else "—")
                c3.metric("P75 P/E", f"{pe['p75_pe']:.1f}x" if pe['p75_pe'] else "—")
                e1, e2, e3 = st.columns(3)
                e1.metric("Median EV/EBITDA", f"{ev['median_ev_ebitda']:.1f}x" if ev['median_ev_ebitda'] else "—")
                e2.metric("P25 EV/EBITDA", f"{ev['p25_ev_ebitda']:.1f}x" if ev['p25_ev_ebitda'] else "—")
                e3.metric("P75 EV/EBITDA", f"{ev['p75_ev_ebitda']:.1f}x" if ev['p75_ev_ebitda'] else "—")
                st.markdown("**Implied MSFT price range**")
                ir = pd.DataFrame([
                    {"Method": "P/E",
                     "Low (P25)": f"${pe['implied_price_p25']:.0f}" if pe['implied_price_p25'] else "—",
                     "Median": f"${pe['implied_price_median']:.0f}" if pe['implied_price_median'] else "—",
                     "High (P75)": f"${pe['implied_price_p75']:.0f}" if pe['implied_price_p75'] else "—"},
                    {"Method": "EV/EBITDA",
                     "Low (P25)": f"${ev['implied_price_p25']:.0f}" if ev['implied_price_p25'] else "—",
                     "Median": f"${ev['implied_price_median']:.0f}" if ev['implied_price_median'] else "—",
                     "High (P75)": f"${ev['implied_price_p75']:.0f}" if ev['implied_price_p75'] else "—"},
                ])
                st.dataframe(ir, use_container_width=True, hide_index=True)
                for p in g["peers"]:
                    if p.get("reason") and p["reason"] != "ok":
                        st.caption(f"⚠️ {p['ticker']}: {p['reason']}")
            st.markdown("#### DCF vs relative valuation")
            base_dcf = analysis["scenarios"]["base"]["intrinsic_per_share_usd"]
            st.caption(f"Driver DCF (base) intrinsic **${base_dcf:.2f}** · Market close **${analysis['market_price']:.2f}**")
            st.info("DCF, P/E and EV/EBITDA are shown separately, not averaged into a single target — "
                    "each embeds different assumptions (DCF uses illustrative WACC/capex; multiples are market-implied).")

    with tab_w:
        wacc_block = result.get("wacc")
        if wacc_block is None:
            st.info("Company-specific WACC is not computed for DEMO (synthetic); the illustrative WACC is used.")
        elif not wacc_block.get("available"):
            st.error("⚠️ Company-specific WACC **unavailable**.")
            st.markdown(f"**Reason:** {wacc_block.get('reason', 'unknown')}")
            st.info("Intrinsic values shown use the **illustrative** (non-company-specific) WACC — this is not a company-specific valuation.")
            irows = []
            for k, v in (wacc_block.get("inputs") or {}).items():
                irows.append({
                    "Input": k,
                    "Status": "available" if v.get("available") else "unavailable",
                    "Detail": ((v.get("source") or "")[:60] if v.get("available") else (v.get("reason") or "")[:80]),
                })
            st.dataframe(pd.DataFrame(irows), use_container_width=True, hide_index=True)
        else:
            calc = wacc_block["calculation"]
            inputs = wacc_block["inputs"]
            st.metric("Company-specific WACC", f"{calc['wacc']:.2%}")
            same = all(abs(cases[c]["wacc"] - calc["wacc"]) < 1e-9 for c in ("bear", "base", "bull"))
            if same:
                st.caption("✅ All three operating scenarios (Bear/Base/Bull) use this same company-specific WACC.")
            else:
                st.warning("Scenario WACCs differ — expected a single company-specific rate.")

            beta_in = inputs.get("beta", {})
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Beta (5y weekly)", f"{beta_in.get('value'):.3f}" if beta_in.get('value') is not None else "—")
            b2.metric("R-squared", f"{beta_in.get('r_squared'):.3f}" if beta_in.get('r_squared') is not None else "—")
            b3.metric("Std. error (β)", f"{beta_in.get('se_beta'):.4f}" if beta_in.get('se_beta') is not None else "—")
            b4.metric("Observations", f"{beta_in.get('n')}" if beta_in.get('n') else "—")
            if beta_in.get("benchmark"):
                bench = f"Benchmark **{beta_in['benchmark']}** · period {beta_in.get('period')}"
                if beta_in.get('beta_2yr') is not None:
                    bench += f" · 2-year beta {beta_in['beta_2yr']:.3f}"
                st.caption(bench)

            st.markdown("#### WACC inputs (source · classification · confidence)")
            def fmt_input(k, v):
                if not v.get("available"):
                    return "unavailable"
                val = v.get("value")
                if k in ("risk_free_rate", "equity_risk_premium", "pre_tax_cost_of_debt", "marginal_tax_rate"):
                    return f"{val:.2%}"
                if k in ("equity_value", "debt_value"):
                    return fmt_b(val)
                return f"{val:.4g}"
            labels = {
                "risk_free_rate": "Risk-free rate", "equity_risk_premium": "Equity risk premium",
                "beta": "Beta", "equity_value": "Equity value (market cap)", "debt_value": "Gross debt",
                "pre_tax_cost_of_debt": "Pre-tax cost of debt", "marginal_tax_rate": "Marginal tax rate",
            }
            irows = []
            for k in ("risk_free_rate", "equity_risk_premium", "beta", "equity_value", "debt_value", "pre_tax_cost_of_debt", "marginal_tax_rate"):
                v = inputs.get(k, {})
                irows.append({
                    "Input": labels.get(k, k),
                    "Value": fmt_input(k, v),
                    "Kind": v.get("kind", "—"),
                    "Confidence": v.get("confidence", "—"),
                    "Source / note": ((v.get("source") or v.get("reason") or "")[:70]),
                })
            st.dataframe(pd.DataFrame(irows), use_container_width=True, hide_index=True)

            rf_src = inputs.get("risk_free_rate", {}).get("source", "")
            if "TNX" in rf_src or "fallback" in rf_src.lower():
                st.warning(f"⚠️ Risk-free rate uses the Yahoo **^TNX** fallback because FRED DGS10 was unavailable. Source: {rf_src}")
            cod = inputs.get("pre_tax_cost_of_debt", {})
            if cod.get("confidence") == "low":
                st.warning("⚠️ Pre-tax cost of debt is a **low-confidence** historical proxy "
                           f"({cod.get('value'):.2%}): {cod.get('limitation', '')}")
            eqv = inputs.get("equity_value", {})
            st.caption(f"Market capitalization uses the point-in-time common share count — source: {eqv.get('source','')} "
                       f"· as-of {eqv.get('period','')}. Diluted shares ({analysis.get('diluted_shares') or 'n/a'}) are used for intrinsic value per share.")

            c1, c2, c3 = st.columns(3)
            c1.metric("Cost of equity", f"{calc['cost_of_equity']:.2%}")
            c2.metric("After-tax cost of debt", f"{calc['after_tax_cost_of_debt']:.2%}")
            c3.metric("Debt weight", f"{calc['debt_weight']:.2%}")
            st.caption(f"Equity weight **{calc['equity_weight']:.2%}** · Debt weight **{calc['debt_weight']:.2%}**")

            st.markdown("#### WACC × terminal-growth sensitivity (intrinsic value per share)")
            sens = analysis.get("sensitivity") or []
            if sens:
                sdf = pd.DataFrame(sens)
                pivot = sdf.pivot(index="terminal_growth", columns="wacc", values="intrinsic_per_share_usd")
                pivot = pivot.sort_index().sort_index(axis=1)
                pivot.index = [f"{g:.1%}" for g in pivot.index]
                pivot.columns = [f"{w:.2%}" for w in pivot.columns]
                st.dataframe(pivot, use_container_width=True)
                st.line_chart(sdf.pivot(index="wacc", columns="terminal_growth", values="intrinsic_per_share_usd"))
                st.caption("WACC always exceeds terminal growth in every cell (guarded by the engine).")
            else:
                st.info("Sensitivity table not generated (company WACC unavailable).")

    with tab_t:
        st.markdown("#### Price history & moving averages")
        st.line_chart(prices[["close", "sma20", "sma50", "sma200"]], height=360)
        st.markdown(f"**SMA20** {result['technical']['sma20']:,.2f} · "
                    f"**SMA50** {result['technical']['sma50']:,.2f} · "
                    f"**SMA200** {result['technical']['sma200']:,.2f} · "
                    f"Trend: **{result['technical']['trend']}**")
        st.markdown("**Rule:** long when SMA20 > SMA50, trade next session (10 bps/trade).")
        t1, t2 = st.columns(2)
        t1.metric("Strategy total return", f"{result['technical']['strategy_total_return_pct']:+.2f}%")
        t2.metric("Buy-and-hold total return", f"{result['technical']['buyhold_total_return_pct']:+.2f}%")
        st.line_chart(prices[["strategy_growth", "buyhold_growth"]].dropna(), height=280)
        st.caption(result['technical']['warning'])
        if result['technical'].get('data_warning'):
            st.warning(result['technical']['data_warning'])

    with tab_s:
        st.markdown("#### DCF assumptions")
        ap = analysis["assumption_provenance"]
        st.markdown(f"- **Growth:** {ap['growth']}\n- **WACC:** {ap['wacc']}\n- **Terminal growth:** {ap['terminal_growth']}")

        st.markdown("#### Source dates & providers")
        prov = result["provenance"]
        fin = prov["financials"]
        cik = fin.get("cik")
        st.markdown(f"- Financial source: **{fin['provider']}**" + (f" (CIK {cik})" if cik else ""))
        st.markdown(f"- Financial URL: {fin.get('url') or 'n/a (synthetic)'}")
        st.markdown(f"- Market source: **{prov['market']['provider']}** · price date {prov['market'].get('price_date')} · realtime={prov['market'].get('realtime')}")
        if has_bridge:
            ref = (fin.get("debt_reconciliation") or {}).get("reference_date")
            if ref:
                st.markdown(f"- Balance-sheet reference date: **{ref}**")

        st.markdown("#### Data classification")
        st.markdown(
            "| Category | Content |\n|---|---|\n"
            "| 🟢 Real historical data | SEC-reported CFO, capex, interest, tax, debt, cash, shares, investments; market close |\n"
            "| 🔵 Derived calculations | FCFF history, DCF, net debt, equity bridge, intrinsic value, P/E |\n"
            "| 🟡 Illustrative assumptions | WACC 11/10/9%, terminal growth 1.5/2/2.5%, ±5% growth spread |\n"
            "| 🟣 Verified note adjustment | Restricted-in-short-term (reconciled case) — only when note-verified |\n"
            "| 🔴 Missing / uncertain | Any `null` fields, excluded tags, and the upper-bound investment case |"
        )

        st.markdown("#### Warnings & limitations")
        for w in fin.get("disclosure_warnings", []):
            st.caption(f"⚠️ {w}")
        for w in fin.get("investment_assumptions", []):
            st.caption(f"⚠️ {w}")
        if has_bridge and bridge.get("restricted_in_short_term_usd"):
            st.info(f"Reconciled case uses note-verified restricted-in-short-term = "
                    f"{fmt_b(bridge['restricted_in_short_term_usd'])} ({bridge.get('reconciled_basis', 'note-verified')}).")
        for lim in result["limitations"]:
            st.caption(f"• {lim}")

        with st.expander("Raw provenance JSON"):
            st.json(prov)

    st.download_button("Download analysis JSON", data=json.dumps(result, indent=2),
                       file_name=f"autoval_{ticker.lower()}.json", mime="application/json")
else:
    st.info("Enter a ticker and click **Analyze**. For a guaranteed offline example, choose **Offline DEMO**.")
