"""Streamlit workspace for reproducible equity valuation."""
from html import escape
import json
import os
import re

import altair as alt
from dotenv import load_dotenv
import pandas as pd
import streamlit as st

from autoval.compare import comparability_flags, comparison_csv, comparison_rows
from autoval.finance import analyze_driver_valuation, dcf_from_fcff
from autoval.forecast import project_fcff
from autoval.pipeline import ROOT, build_analysis
from autoval.report import build_report_markdown
from autoval.reverse import reverse_dcf
from verify_output import check_report

SOURCE_REPO = "https://github.com/yzamyyu-cyber/autoval-ai-pro"
CASES = ("bear", "base", "bull")


def usd(value):
    return f"{'−' if value < 0 else ''}${abs(value):,.2f}" if pd.notna(value) else "—"


def pct(value):
    return f"{value:.2%}" if value is not None else "—"


def multiple(value):
    return f"{value:.1f}×" if value is not None else "—"


def run_controls():
    """Keep the last successful report visible while a new run is pending or fails."""
    configured_contact = os.environ.get("SEC_USER_AGENT", "").strip()
    contact_ready = "@" in configured_contact and "your-school-email@example.edu" not in configured_contact
    if "sec_contact_input" not in st.session_state:
        st.session_state.sec_contact_input = st.session_state.get("sec_contact_email", "")

    def set_ticker(ticker):
        st.session_state.live_ticker = ticker

    msft, hd, _ = st.columns([1, 1, 3])
    msft.button("Microsoft (MSFT)", on_click=set_ticker, args=("MSFT",), width="stretch")
    hd.button("Home Depot (HD)", on_click=set_ticker, args=("HD",), width="stretch")
    with st.form("research"):
        entry, contact = st.columns(2)
        with entry:
            ticker = st.text_input("U.S. stock ticker", placeholder="e.g. MSFT, HD, AAPL",
                                   max_chars=10, key="live_ticker")
        with contact:
            email_label = "SEC contact email (optional override)" if contact_ready else "SEC contact email (for live analysis)"
            email = st.text_input(email_label, type="password", max_chars=254, key="sec_contact_input",
                                  help="The app uses this email for SEC requests during this browser session.")
        live, demo, _ = st.columns([1, 1, 2])
        with live:
            run_live = st.form_submit_button("Run live analysis", type="primary", width="stretch")
        with demo:
            run_demo = st.form_submit_button("Load offline demo", width="stretch")

    if run_live:
        ticker = ticker.strip().upper()
        email = email.strip()
        if not ticker or not ticker.isascii() or not ticker.isalnum():
            st.error("Choose a company above or enter a ticker with 1–10 letters or digits.")
        elif email and (not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not email.isascii()):
            st.warning("Enter a valid contact email in the SEC contact field.")
        elif not email and not contact_ready:
            st.warning("Enter your SEC contact email above, then click Run live analysis.")
        else:
            user_agent = f"AutoVal AI Pro {email}" if email else configured_contact
            st.session_state.sec_contact_email = email
            with st.spinner(f"Reading filings and market data for {ticker}…"):
                try:
                    st.session_state.report = build_analysis(ticker, "live", user_agent)
                except Exception as exc:
                    message = str(exc).replace(user_agent, "[SEC contact]")
                    if email:
                        message = message.replace(email, "[SEC contact]")
                    st.error(f"{ticker} analysis stopped. {message}")
    if run_demo or "report" not in st.session_state:
        st.session_state.report = build_analysis("DEMO", "demo")

    return st.session_state.report


def overview_header(result):
    analysis = result["analysis"]
    base = analysis["scenarios"]["base"]
    demo = result["mode"] == "demo"
    company = "Example Holdings" if demo else result["company"]
    source = "Synthetic data" if demo else "Delayed market data"
    price_label = "Reference price" if demo else "Market close"
    forecast = "Driver-based FCFF" if result["forecast_basis"] == "driver" else "Constant-growth FCFF"
    st.markdown(
        f"""
        <div class="av-hero">
          <div class="av-kicker">{escape(result['ticker'])} &nbsp;/&nbsp; {source}</div>
          <h1>{escape(company)}</h1>
          <p>Equity valuation report</p>
          <div class="av-meta">
            <span>{price_label} date {escape(str(analysis['price_date'] or 'unavailable'))}</span>
            <span>Fiscal year ended {escape(str(analysis['financial_asof'] or 'unavailable'))}</span>
            <span>{forecast}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metrics = (
        ("Base DCF per share", usd(base["intrinsic_per_share_usd"]), "Discounted cash flow", "accent"),
        (price_label, usd(analysis["market_price"]), "Fictional quote" if demo else "Unadjusted daily close", ""),
        ("DCF vs. reference" if demo else "DCF vs. close",
         f"{base['upside_vs_price_pct']:+.1f}%", "Base-case gap", ""),
        ("Base WACC", pct(base["wacc"]), analysis["wacc_basis"].capitalize(), ""),
    )
    cards = "".join(
        f'<div class="av-metric {style}"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>'
        for label, value, note, style in metrics
    )
    st.markdown(f'<div class="av-metrics">{cards}</div>', unsafe_allow_html=True)


def valuation_chart(cases, price, benchmark):
    labels = ["Bear", "Base", "Bull", benchmark]
    frame = pd.DataFrame({
        "Case": labels,
        "USD per share": [cases[k]["intrinsic_per_share_usd"] for k in CASES] + [price],
    })
    chart = alt.Chart(frame).encode(
        x=alt.X("USD per share:Q", axis=alt.Axis(format="$,.0f", tickCount=5)),
        y=alt.Y("Case:N", sort=labels, axis=alt.Axis(title=None, labelPadding=8)),
    )
    bars = chart.mark_bar(size=20, cornerRadius=3).encode(
        color=alt.Color("Case:N", legend=None,
                        scale=alt.Scale(domain=labels, range=["#a5b8c4", "#0b7c70", "#75aa9e", "#274b63"])),
        tooltip=[alt.Tooltip("Case:N"), alt.Tooltip("USD per share:Q", format="$,.2f")],
    )
    return bars.properties(height=182).configure_view(strokeWidth=0)


def render_overview(result, verification):
    analysis = result["analysis"]
    cases = analysis["scenarios"]
    base = cases["base"]
    benchmark = "Reference" if result["mode"] == "demo" else "Market close"
    chart, model = st.columns([2, 1])
    with chart, st.container(border=True):
        st.subheader("Valuation range")
        st.caption("Bear, base and bull DCF estimates in USD per share.")
        st.altair_chart(
            valuation_chart(cases, analysis["market_price"], benchmark),
            theme=None, width="stretch",
        )
    with model, st.container(border=True):
        st.subheader("Model checks")
        if verification["passed"]:
            st.success("Independent DCF check passed")
        else:
            st.error("Independent DCF check needs review")
        st.caption("Decimal arithmetic checks all three scenarios to within one cent per share.")
        st.metric("Terminal value / enterprise value", pct(base["terminal_weight_of_ev"]))
        st.caption("Share of enterprise value assigned to cash flows beyond the explicit forecast.")

    st.subheader("DCF scenarios")
    st.dataframe(pd.DataFrame([
        {"Scenario": case.title(), "DCF / share": usd(cases[case]["intrinsic_per_share_usd"]),
         "Gap to price": f"{cases[case]['upside_vs_price_pct']:+.1f}%", "WACC": pct(cases[case]["wacc"]),
         "FCFF growth": pct(cases[case]["growth"]) if cases[case].get("growth") is not None else "Driver-based",
         "Terminal growth": pct(cases[case]["terminal_growth"])}
        for case in CASES
    ]), hide_index=True, width="stretch")

    with st.expander("Comparable-company valuation"):
        render_peers(result)


def render_peers(result):
    relative = result.get("relative")
    if not relative:
        st.info("Peer estimates are unavailable for this run.")
        return
    target = relative["target"]
    st.caption(f"Target TTM EPS {usd(target.get('ttm_eps'))} · TTM EBITDA {usd(target.get('ttm_ebitda'))}")
    for group in relative["groups"].values():
        st.markdown(f"**{group['label'].replace('_', ' ').title()}** · {group['sample_size']} valued peers")
        if group["sample_size"] < 3:
            st.caption("Limited observations. Peer medians are suppressed.")
        else:
            pe, ev = group["pe"], group["ev_ebitda"]
            st.caption(f"P/E median {multiple(pe['median_pe'])} · Implied {usd(pe['implied_price_median'])} per share ({pe['sample_size']} usable)")
            st.caption(f"EV/EBITDA median {multiple(ev['median_ev_ebitda'])} · Implied {usd(ev['implied_price_median'])} per share ({ev['sample_size']} usable)")
        if group["peers"]:
            st.dataframe(pd.DataFrame([
                {"Peer": peer["ticker"], "P/E": multiple(peer.get("pe")),
                 "EV/EBITDA": multiple(peer.get("ev_ebitda")), "Close date": peer.get("price_date"),
                 "Data notes": peer.get("reason")}
                for peer in group["peers"]
            ]), hide_index=True, width="stretch")


def render_scenario_lab(result):
    analysis = result["analysis"]
    base = analysis["scenarios"]["base"]
    run_key = f"{result['ticker']}_{result['run_utc']}"
    with st.container(border=True):
        st.subheader("Reprice the base case")
        st.caption("Adjust discount and terminal growth rates in percentage points. "
                   "The projected cash flows, share count and net debt stay fixed.")
        wacc_col, growth_col = st.columns(2)
        with wacc_col:
            wacc_shift = st.slider("WACC adjustment", -3.0, 3.0, 0.0, .25, format="%+.2f pp", key=f"wacc_{run_key}")
        with growth_col:
            growth_shift = st.slider("Terminal growth adjustment", -2.0, 2.0, 0.0, .25, format="%+.2f pp", key=f"growth_{run_key}")
        wacc = base["wacc"] + wacc_shift / 100
        growth = base["terminal_growth"] + growth_shift / 100
        st.caption(f"Applied assumptions · WACC {pct(wacc)} · Terminal growth {pct(growth)}")
        if 0 < wacc < 1 and -.1 <= growth < wacc:
            repriced = dcf_from_fcff(base["forecast_fcff_usd"], base["shares"], base["net_debt_usd"], wacc, growth)
            changed, original, dependence = st.columns(3)
            delta = repriced["intrinsic_per_share_usd"] - base["intrinsic_per_share_usd"]
            changed.metric("What-if DCF / share", usd(repriced["intrinsic_per_share_usd"]))
            original.metric("Change from base / share", f"{'−' if delta < 0 else '+' if delta > 0 else ''}{usd(abs(delta))}")
            dependence.metric("What-if terminal value / EV", pct(repriced["terminal_weight_of_ev"]))
        else:
            st.warning("Choose a positive WACC below 100% and a terminal growth rate below WACC.")

    if analysis.get("sensitivity"):
        st.subheader("WACC and terminal growth grid")
        values = pd.DataFrame(analysis["sensitivity"]).pivot_table(
            index="terminal_growth", columns="wacc", values="intrinsic_per_share_usd",
        )
        values.index = values.index.map(pct)
        values.columns = values.columns.map(pct)
        values.index.name = "Terminal growth"
        st.dataframe(values.apply(lambda column: column.map(usd)), width="stretch")

    render_capex_lab(analysis, run_key)


def render_capex_lab(analysis, run_key):
    """Reprice one base forecast after changing just its CapEx-to-revenue driver."""
    st.subheader("CapEx sensitivity")
    if analysis.get("forecast"):
        st.caption("Uses the current company's base operating forecast.")
    else:
        st.caption("Uses a separate fictional manufacturing example with a driver-based forecast.")
        demo_stock = {"ticker": "CAPEX", "market_price": 100, "shares": 100e6, "net_debt": 1e9}
        demo_history = {
            "revenue": [8e9, 9e9, 10e9],
            "operating_income": [2.4e9, 2.7e9, 3e9],
            "da": [.4e9, .45e9, .5e9],
            "capex": [.64e9, .9e9, 1.2e9],
            "nwc": [1e9],
        }
        analysis = analyze_driver_valuation(demo_stock, demo_history)

    forecast = analysis["forecast"]["base"]
    base = analysis["scenarios"]["base"]
    base_ratio = forecast["drivers"]["capex_ratio"]
    with st.expander("CapEx and cash-flow formulas"):
        st.latex(r"\mathrm{CapEx}_t = \mathrm{Revenue}_t \times \mathrm{CapEx\ ratio}")
        st.latex(r"\mathrm{FCFF}_t = \mathrm{EBIT}_t(1-T) + \mathrm{D\&A}_t - \mathrm{CapEx}_t - \Delta\mathrm{NWC}_t")
    st.caption(f"Base CapEx is {pct(base_ratio)} of revenue. All other forecast assumptions, including WACC and terminal growth, stay fixed.")
    ratio = st.number_input(
        "CapEx as a percentage of revenue", min_value=0.0, value=base_ratio * 100,
        step=1.0, format="%.2f", key=f"capex_{run_key}",
    ) / 100
    drivers = {**forecast["drivers"], "capex_ratio": ratio}
    try:
        rows = project_fcff(forecast["base_revenue"], forecast["base_nwc"], base["years"], **drivers)
        stressed = dcf_from_fcff(
            [row["fcff"] for row in rows], base["shares"], base["net_debt_usd"],
            base["wacc"], base["terminal_growth"],
        )
    except (ValueError, ArithmeticError):
        st.warning("This CapEx assumption produces an undefined valuation. Try a lower percentage.")
        return
    original, updated, change = st.columns(3)
    base_price = base["intrinsic_per_share_usd"]
    price = stressed["intrinsic_per_share_usd"]
    original.metric("CapEx lab base DCF / share", usd(base_price))
    updated.metric("CapEx-adjusted DCF / share", usd(price))
    change.metric("Change from CapEx lab base", usd(price - base_price))
    if capex := analysis.get("capex_sensitivity"):
        latest_price = capex["intrinsic_per_share_usd"]["base"]
        st.caption(f"Latest fiscal-year CapEx intensity {pct(capex['high_capex_ratio'])} implies {usd(latest_price)} per share.")


def render_market_expectations(result):
    st.subheader("What cash-flow growth would justify this price?")
    st.caption("Reverse DCF holds the base forecast's first year of free cash flow to the firm (FCFF) fixed. "
               "It solves for constant annual FCFF growth from year 2 through the end of the forecast.")
    analysis = result["analysis"]
    run_key = f"{result['ticker']}_{result['run_utc']}"
    label = "Fictional reference price" if result["mode"] == "demo" else "Delayed market close"
    st.caption(f"{label} {usd(analysis['market_price'])} · {analysis['price_date']}")
    price = None
    if st.checkbox("Use a hypothetical price", key=f"custom_price_{run_key}"):
        price = st.number_input(
            "Target price (USD per share)", min_value=0.0,
            value=float(analysis["market_price"]), format="%.2f", key=f"target_price_{run_key}",
        )

    try:
        expectation = reverse_dcf(result, price)
    except ValueError as exc:
        st.info(str(exc))
        return

    implied, base, target = st.columns(3)
    implied.metric("Implied annual FCFF growth", pct(expectation["implied_fcff_growth"]))
    base.metric("Base forecast FCFF CAGR", pct(expectation["base_forecast_fcff_cagr"]))
    target.metric("Target price per share", usd(expectation["target_price_usd"]))
    st.caption("The base CAGR measures growth between the first and last projected years. "
               "The driver forecast can follow a different year-by-year path.")
    st.markdown(
        f"**Fixed inputs** · Year 1 FCFF ${expectation['first_year_fcff_usd'] / 1e9:,.2f}B"
        f" · WACC {pct(expectation['wacc'])} ({expectation['wacc_basis']})"
        f" · Terminal growth {pct(expectation['terminal_growth'])}"
    )
    st.caption(
        f"Net debt ${expectation['net_debt_usd'] / 1e9:,.2f}B · "
        f"Shares {expectation['shares']:,.0f} · {expectation['forecast_years']}-year forecast"
    )
    st.success(f"Repriced at {usd(expectation['modeled_price_usd'])} per share using the implied growth. "
               "The model matches the target within $0.01.")
    st.download_button(
        "Download reverse DCF JSON", json.dumps(expectation, indent=2, allow_nan=False),
        f"autoval_{result['ticker'].lower()}_reverse_dcf.json", "application/json",
    )


def render_financials(result, prices):
    analysis = result["analysis"]
    st.subheader("Projected free cash flow to the firm")
    base = analysis["scenarios"]["base"]
    if forecast := analysis.get("forecast"):
        drivers = forecast["base"]["drivers"]
        st.caption(f"Base drivers · Revenue growth {pct(drivers['revenue_growth'])} · Operating margin {pct(drivers['operating_margin'])} · CapEx / revenue {pct(drivers['capex_ratio'])}")
        columns = {"revenue": "Revenue", "ebit": "EBIT", "nopat": "NOPAT", "da": "D&A",
                   "capex": "CapEx", "change_in_nwc": "ΔNWC", "fcff": "FCFF"}
        forecast_frame = pd.DataFrame(forecast["base"]["rows"])
        table = (forecast_frame.set_index("year")[list(columns)] / 1e9).round(2).rename(columns=columns)
        table.index.name = "Year"
        st.caption("USD billions · FCFF = NOPAT + D&A − CapEx − ΔNWC")
        st.dataframe(table, width="stretch")
    else:
        st.caption(f"Constant-growth forecast · Annual FCFF growth {pct(base['growth'])}")
    projected = pd.DataFrame({
        "Year": range(1, base["years"] + 1),
        "FCFF (USD billions)": [flow / 1e9 for flow in base["forecast_fcff_usd"]],
    })
    st.bar_chart(projected, x="Year", y="FCFF (USD billions)", height=190)

    with st.expander("Enterprise-to-equity bridge"):
        st.markdown(f"Enterprise value **{usd(base['enterprise_value_usd'])}** − "
                    f"net debt **{usd(base['net_debt_usd'])}** = equity value **{usd(base['equity_value_usd'])}**.")
        st.caption(f"{base['shares']:,.0f} shares · Base DCF {usd(base['intrinsic_per_share_usd'])} per share")
        for variant in ("conservative", "upper", "reconciled"):
            value = base.get(f"intrinsic_per_share_usd_{variant}")
            if value is not None:
                st.caption(f"Investment-adjusted {variant} case · {usd(value)} per share")

    with st.expander("Cost of capital"):
        wacc = result.get("wacc") or {}
        st.write(analysis["assumption_provenance"]["wacc"])
        if wacc.get("available"):
            c = wacc["calculation"]
            st.markdown(f"Cost of equity **{pct(c['cost_of_equity'])}** · After-tax cost of debt "
                        f"**{pct(c['after_tax_cost_of_debt'])}** · Equity weight **{pct(c['equity_weight'])}**")
            st.caption(f"Risk-free rate {pct(c['risk_free_rate'])} · Beta {c['beta']:.2f} · Equity risk premium {pct(c['equity_risk_premium'])}")

    with st.expander("Price history and illustrative backtest"):
        st.line_chart(prices[["close", "sma20", "sma50", "sma200"]], height=240)
        technical = result["technical"]
        st.caption(f"Strategy {technical['strategy_total_return_pct']:+.2f}% · "
                   f"Buy-and-hold {technical['buyhold_total_return_pct']:+.2f}%")
        st.caption(technical["warning"])
        if technical.get("data_warning"):
            st.caption(technical["data_warning"])


def render_evidence(result, verification):
    st.subheader("Independent DCF recomputation")
    st.caption("Decimal arithmetic re-discounts the exported cash flows and terminal value. "
               "This check tests arithmetic and scenario ordering. Filing inputs and forecast assumptions need separate review.")
    st.dataframe(pd.DataFrame([
        {"Scenario": check["case"].title(), "Engine USD": f"{check['engine_intrinsic_usd']:.6f}",
         "Independent USD": f"{check['independent_intrinsic_usd']:.6f}",
         "Absolute error USD": f"{check['abs_difference_usd']:.2e}", "Result": "Pass" if check["pass"] else "Review"}
        for check in verification["checks"]
    ]), hide_index=True, width="stretch")
    ordering = "pass" if verification["scenario_order_pass"] else "review"
    st.caption(f"Tolerance $0.01 per share · Scenario ordering {ordering}")

    st.subheader("Sources and assumptions")
    fin, market = (result["provenance"][key] for key in ("financials", "market"))
    st.markdown(f"**Financials** · {fin['provider']}  \n**Prices** · {market['provider']}")
    if fin.get("url"):
        st.link_button("Open SEC company facts", fin["url"])
    st.caption(f"Run timestamp (UTC) · {result['run_utc']}")
    with st.expander("Provenance and limitations"):
        for key, value in result["analysis"]["assumption_provenance"].items():
            st.write(f"{key.replace('_', ' ').capitalize()} · {value}")
        for limitation in result.get("limitations", []) + fin.get("disclosure_warnings", []):
            st.write(f"• {limitation}")

    st.subheader("Export evidence")
    st.caption("Exports contain the original report assumptions. Scenario Lab inputs apply to the what-if view.")
    name = f"autoval_{result['ticker'].lower()}_{result['mode']}"
    report, analysis, check = st.columns(3)
    report.download_button("Research report", build_report_markdown(result), f"{name}.md", "text/markdown", width="stretch")
    analysis.download_button("Analysis JSON", json.dumps(result, indent=2), f"{name}.json", "application/json", width="stretch")
    check.download_button("Verification JSON", json.dumps(verification, indent=2), f"{name}_verification.json", "application/json", width="stretch")


def render_comparison():
    st.title("Compare Companies")
    source = st.radio("Analysis source", ("Bundled examples", "Saved analysis files"), horizontal=True)
    if source == "Bundled examples":
        st.caption("Both companies and all prices are fictional.")
        reports = [build_analysis(ticker, "demo")[0] for ticker in ("DEMO", "DEMO2")]
    else:
        left, right = st.columns(2)
        first = left.file_uploader("First analysis JSON", type="json")
        second = right.file_uploader("Second analysis JSON", type="json")
        if first is None or second is None:
            st.info("Upload two AutoVal Analysis JSON exports.")
            return
        try:
            reports = [json.loads(upload.getvalue()) for upload in (first, second)]
        except ValueError:
            st.error("Both files must contain valid JSON.")
            return

    def values(row):
        currency = row["currency"]
        pe_group = row["peer_group"]
        return [
            str(row["company"]).split(" (synthetic data")[0], row["mode"], currency,
            f"{row['price']:,.2f}", row["price_date"] or "—", row["financial_asof"] or "—",
            f"{row['base_dcf_per_share']:,.2f}", usd(row["intrinsic_price_gap_usd"]),
            f"{row['valuation_gap_pct']:+.2f}%",
            pct(row["wacc"]), row["wacc_basis"] or "—", pct(row["forecast_growth"]),
            row["forecast_growth_basis"], pct(row["implied_fcff_growth"]),
            pe_group.replace("_", " ").title() if pe_group else "—",
            str(row["peer_sample_size"]) if row["peer_sample_size"] is not None else "—",
            multiple(row["median_pe"]), multiple(row["median_ev_ebitda"]),
        ]

    try:
        rows = comparison_rows(reports)
        first, second = [values(row) for row in rows]
        csv_data = comparison_csv(reports)
    except (ValueError, KeyError, TypeError, AttributeError):
        st.error("This comparison needs two complete AutoVal Analysis JSON exports.")
        return

    for message in comparability_flags(rows):
        st.warning(message)
    labels = [
        "Company", "Data mode", "Currency", "Reference or close price", "Price date", "Fiscal period end",
        "Base DCF per share", "Valuation gap (USD)", "Valuation gap (%)",
        "Base WACC", "WACC basis", "Base forecast growth",
        "Forecast growth measure", "Price-implied FCFF growth", "Peer group",
        "Valued peers", "Median P/E", "Median EV/EBITDA",
    ]
    headers = [str(row["ticker"]) for row in rows]
    if headers[0] == headers[1]:
        headers = [f"{ticker} ({index})" for index, ticker in enumerate(headers, start=1)]
    st.table(pd.DataFrame({"Metric": labels, headers[0]: first, headers[1]: second}).set_index("Metric"))
    st.caption("Valuation gap = (base DCF per share ÷ reference or close price − 1) × 100.")
    st.download_button("Download comparison CSV", csv_data, "autoval_comparison.csv", "text/csv")


def main():
    st.set_page_config(page_title="AutoVal AI Pro", page_icon="📈", layout="wide")
    load_dotenv(ROOT / ".env", override=False)
    styles = (ROOT / ".streamlit" / "workspace.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="av-top"><div class="av-brand"><span class="av-mark">AV</span>AutoVal AI Pro</div>'
        f'<a href="{SOURCE_REPO}" target="_blank" rel="noopener noreferrer">GitHub source</a></div>',
        unsafe_allow_html=True,
    )
    view = st.radio("Workspace", ("Research", "Compare Companies"), horizontal=True, label_visibility="collapsed")
    if view == "Compare Companies":
        render_comparison()
        return
    result, prices = run_controls()
    verification = check_report(result)
    overview_header(result)
    overview, lab, expectations, financials, evidence = st.tabs(
        ["Overview", "Scenario Lab", "Market Expectations", "Financials", "Evidence & Exports"],
    )
    with overview:
        render_overview(result, verification)
    with lab:
        render_scenario_lab(result)
    with expectations:
        render_market_expectations(result)
    with financials:
        render_financials(result, prices)
    with evidence:
        render_evidence(result, verification)
    st.caption("Educational research prototype for U.S. nonfinancial SEC filers.")


if __name__ == "__main__":
    main()
