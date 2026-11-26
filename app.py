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


def valuation_display(value):
    """Format a per-share DCF value for display. Negative modeled equity is NOT shown as
    an ordinary negative stock price; it is labeled instead. Signed values remain in the
    raw exports and audit details."""
    if value is None or not pd.notna(value):
        return "—"
    if value < 0:
        return "N/A — Negative modeled equity"
    return usd(value)


def apply_basis(result, basis):
    """Return a copy of `result` with the selected valuation basis swapped in.

    "ttm" uses the latest trailing-twelve-month period; "annual" uses the annual FY.
    Swaps scenarios, forecast and multi-stage so every downstream view stays consistent.
    """
    analysis = result["analysis"]
    ttm = analysis.get("ttm")
    if basis == "ttm" and ttm is not None:
        new_analysis = dict(analysis)
        new_analysis["scenarios"] = {c: ttm[c] for c in CASES}
        new_analysis["forecast"] = ttm.get("forecast", analysis.get("forecast"))
        new_analysis["multistage"] = ttm.get("multistage", analysis.get("multistage"))
        new_analysis["valuation_basis"] = "ttm"
        # NOTE: `financial_asof` intentionally NOT overwritten — it remains the latest
        # completed fiscal year. The TTM period is exposed separately via
        # `valuation_basis_asof` / the "Latest reported quarter" field.
        new_result = dict(result)
        new_result["analysis"] = new_analysis
        new_result["valuation_basis"] = "ttm"
        new_result["valuation_basis_asof"] = ttm.get("asof")
        return new_result
    return result


def render_freshness_notice(result):
    """Reusable freshness warning, shown consistently across every analysis view."""
    freshness = result.get("freshness") or {}
    if freshness.get("status") == "newer-results-available":
        st.warning(
            f"⚠️ **Newer results available** — an earnings release covering "
            f"{freshness.get('newer_earnings_report_date') or freshness.get('newer_earnings_release')} "
            f"is later than the latest periodic filing "
            f"({freshness.get('latest_periodic_report_date') or freshness.get('latest_periodic_filing')}). "
            f"This valuation uses the latest complete periodic filing; the newer release is not yet "
            f"reconciled into the model.")
    elif freshness.get("status") == "newer-disclosure-period-unconfirmed":
        st.warning(
            "⚠️ **Newer disclosure detected — reporting period unconfirmed.** A later 8-K earnings "
            "release exists, but its financial reporting period could not be confirmed from the "
            "exhibit. This valuation uses the latest complete periodic filing.")


def render_data_dates(result):
    """Compact panel of actual financial / market / WACC periods and saved-data status."""
    analysis = result["analysis"]
    fin = ((result.get("provenance") or {}).get("financials") or {})
    wacc = result.get("wacc") or {}
    rows = [
        ("Valuation basis", f"{result.get('valuation_basis', 'annual')} (as of {result.get('valuation_date') or '—'})"),
        ("Latest completed FY", str(analysis.get("financial_asof") or "—")),
        ("Latest reported quarter (TTM end)", str((analysis.get("ttm") or {}).get("asof") or "—")),
        ("Balance-sheet date", str((fin.get("cash") or {}).get("end") or "—")),
        ("Market price date", str(analysis.get("price_date") or "—")),
    ]
    inp = wacc.get("inputs") or {}
    for key, label in (("risk_free_rate", "Risk-free rate period"),
                       ("equity_risk_premium", "ERP period"),
                       ("beta", "Beta period")):
        p = inp.get(key) or {}
        rows.append((label, str(p.get("period") or p.get("source") or "—")))
    rows.append(("Saved-data status", "live retrieval" if result.get("mode") == "live" else "synthetic demo"))
    render_freshness_notice(result)
    with st.expander("Data periods & dates"):
        st.table(pd.DataFrame(rows, columns=["Item", "Value"]).set_index("Item"))
        st.caption(
            "Forecast cash flows are discounted using full-year periods from the valuation date "
            "(a rolling-forward simplification, no fiscal-stub adjustment). The intrinsic value and "
            "the market price are therefore non-contemporaneous approximations.")


def render_quality_notice(result):
    """Consistent reliability banner reused across every analysis view.

    Data-quality concerns lower confidence; model-suitability issues are
    objective reasons the forecast model cannot support a headline valuation
    (the raw mechanical estimate is preserved for audit); model-risk heuristics
    (negative growth, terminal-value dependence, inconsistent reinvestment) are
    surfaced as warnings but never suppress the estimate on their own.
    """
    from autoval.quality import assess_valuation_quality
    q = assess_valuation_quality(result)
    if q["state"] == "unsuitable":
        st.error("**Model Review Required** — material model limitations remain unresolved; "
                 "this valuation cannot support a reliable headline. The mechanical estimate "
                 "is preserved below for audit.")
        for reason in q["unsuitability"]:
            st.caption(f"• {reason}")
    elif q["state"] == "low_confidence":
        st.warning("**Low confidence** — documented data-quality concerns prevent presenting "
                   "this valuation as a reliable headline estimate.")
        for reason in q["data_quality"]:
            st.caption(f"• {reason}")
    elif q["state"] == "unavailable":
        st.error("Valuation unavailable — required inputs or calculations are missing or invalid.")
    for reason in q["model_suitability"]:
        st.info(f"Model-risk note: {reason}")
    return q


def run_controls():
    """Keep the last successful report visible while a new run is pending or fails."""
    # Offline fixture harness (deterministic demo). The bundled companies are EXAMPLES; a
    # general live ticker search is always available below them (never a hardcoded limit).
    fixture_ticker = os.environ.get("AUTOVAL_FIXTURE_TICKER", "").strip().upper()
    demo_result = demo_prices = None
    if fixture_ticker:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tests"))
        from provider_fixture import build_from_fixture
        demo_companies = ("MSFT", "AMZN", "AAPL", "HD", "GOOGL", "TSLA", "NVDA")
        selected = st.selectbox("Offline demo company", demo_companies,
                                index=demo_companies.index(fixture_ticker)
                                if fixture_ticker in demo_companies else 0,
                                key="demo_company_ui")
        fixture_mode = os.environ.get("AUTOVAL_FIXTURE_MARKET_MODE", "current").strip() or "current"
        demo_result, demo_prices = build_from_fixture(selected, fixture_mode)

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

    # Market-data source (advanced). Default is a genuine live fetch. The user may
    # explicitly select a dated saved snapshot or illustrative (hypothetical) assumptions.
    # A provider failure is NEVER silently converted into illustrative assumptions.
    market_mode_choice = st.radio(
        "Market data source", ("Live (current)", "Saved snapshot", "Illustrative (hypothetical)"),
        horizontal=True, index=0, key="market_mode_ui",
        help="Live (current): fetch a genuine close. Saved snapshot: use a genuine dated "
             "historical close you provide. Illustrative: hypothetical assumptions — any "
             "hypothetical price is stored separately and never shown as a real market price.")
    saved_price = saved_price_date = illustrative_price = None
    market_mode_arg = None
    if market_mode_choice == "Saved snapshot":
        c_price, c_date = st.columns(2)
        saved_price = c_price.number_input("Saved close (USD)", min_value=0.0, value=100.0,
                                           format="%.2f", key="saved_price_ui")
        saved_price_date = c_date.text_input("Observation date (YYYY-MM-DD)",
                                             placeholder="2026-11-10", key="saved_price_date_ui")
        market_mode_arg = "saved"
    elif market_mode_choice == "Illustrative (hypothetical)":
        illustrative_price = st.number_input("Hypothetical price (USD)", min_value=0.0,
                                             value=100.0, format="%.2f", key="illustrative_price_ui")
        market_mode_arg = "illustrative"

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
            kwargs = {}
            if market_mode_arg is not None:
                kwargs["market_mode"] = market_mode_arg
                if market_mode_arg == "saved":
                    kwargs["saved_price"] = saved_price
                    kwargs["saved_price_date"] = saved_price_date or None
                elif market_mode_arg == "illustrative":
                    kwargs["illustrative_price"] = illustrative_price
            with st.spinner(f"Reading filings and market data for {ticker}…"):
                try:
                    st.session_state.report = build_analysis(ticker, "live", user_agent, **kwargs)
                    st.session_state.failed_ticker = None
                except Exception as exc:
                    message = str(exc).replace(user_agent, "[SEC contact]")
                    if email:
                        message = message.replace(email, "[SEC contact]")
                    st.error(f"{ticker} analysis stopped. {message}")
                    st.session_state.failed_ticker = ticker
    if run_demo or "report" not in st.session_state:
        if demo_result is not None:
            # offline demo company (fixture)
            st.session_state.report = (demo_result, demo_prices)
        else:
            st.session_state.report = build_analysis("DEMO", "demo")
        st.session_state.failed_ticker = None

    return st.session_state.report


def overview_header(result):
    analysis = result["analysis"]
    base = analysis["scenarios"]["base"]
    demo = result["mode"] == "demo"
    company = "Example Holdings" if demo else result["company"]
    source = "Synthetic data" if demo else "Delayed market data"
    price_label = "Reference price" if demo else "Market close"
    forecast = "Driver-based FCFF" if result["forecast_basis"] == "driver" else "Constant-growth FCFF"
    bs_asof = (((result.get("provenance") or {}).get("financials") or {}).get("cash") or {}).get("end")
    st.markdown(
        f"""
        <div class="av-hero">
          <div class="av-kicker">{escape(result['ticker'])} &nbsp;/&nbsp; {source}</div>
          <h1>{escape(company)}</h1>
          <p>Equity valuation report</p>
          <div class="av-meta">
            <span>{price_label} date {escape(str(analysis['price_date'] or 'unavailable'))}</span>
            <span>Fiscal year ended {escape(str(analysis['financial_asof'] or 'unavailable'))}</span>
            <span>Latest reported quarter {escape(str(bs_asof or 'unavailable'))}</span>
            <span>{forecast}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    from autoval.quality import assess_valuation_quality
    quality = assess_valuation_quality(result)
    state = quality["state"]
    if state == "unsuitable":
        dcf_value, dcf_note, gap_value = "N/A — Model Review Required", "Reliability policy flag", "—"
    elif state == "low_confidence":
        dcf_value, dcf_note, gap_value = "N/A — Low Confidence", "Reliability policy flag", "—"
    elif state == "unavailable":
        dcf_value, dcf_note, gap_value = "N/A — Unavailable", "Reliability policy flag", "—"
    else:
        upside = base.get("upside_vs_price_pct")
        gap_value = f"{upside:+.1f}%" if upside is not None else "N/A"
        dcf_value, dcf_note = usd(base["intrinsic_per_share_usd"]), "Discounted cash flow"
    dcf_note = dcf_note + (" · TTM/quarterly basis" if analysis.get("valuation_basis") == "ttm" else " · annual basis")
    metrics = (
        ("Base DCF per share", dcf_value, dcf_note, "accent"),
        (price_label, usd(analysis["market_price"]) if (demo or result.get("market_mode", "current") in ("current", "saved")) else "N/A",
         "Fictional quote" if demo else ("Unadjusted daily close" if result.get("market_mode", "current") in ("current", "saved") else "No genuine market price"), ""),
        ("DCF vs. reference" if demo else "DCF vs. close",
         gap_value if (demo or result.get("market_mode", "current") in ("current", "saved")) else "N/A", "Base-case gap", ""),
        ("Base WACC", pct(base["wacc"]), (analysis.get("wacc_basis") or result.get("wacc_basis") or "illustrative").capitalize(), ""),
    )
    cards = "".join(
        f'<div class="av-metric {style}"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>'
        for label, value, note, style in metrics
    )
    st.markdown(f'<div class="av-metrics">{cards}</div>', unsafe_allow_html=True)


def valuation_chart(cases, price, benchmark):
    # Negative modeled equity is OMITTED from the chart (not shown as a zero-length
    # bar); the signed value is retained in the raw export and audit details.
    colors = {"Bear": "#a5b8c4", "Base": "#0b7c70", "Bull": "#75aa9e", benchmark: "#274b63"}
    entries = []
    for k in CASES:
        v = cases[k]["intrinsic_per_share_usd"]
        if v >= 0:
            entries.append((k.title(), v))
    entries.append((benchmark, price))
    labels = [e[0] for e in entries]
    frame = pd.DataFrame({"Case": labels, "USD per share": [e[1] for e in entries]})
    chart = alt.Chart(frame).encode(
        x=alt.X("USD per share:Q", axis=alt.Axis(format="$,.0f", tickCount=5)),
        y=alt.Y("Case:N", sort=labels, axis=alt.Axis(title=None, labelPadding=8)),
    )
    bars = chart.mark_bar(size=20, cornerRadius=3).encode(
        color=alt.Color("Case:N", legend=None,
                        scale=alt.Scale(domain=labels, range=[colors.get(l, "#274b63") for l in labels])),
        tooltip=[alt.Tooltip("Case:N"), alt.Tooltip("USD per share:Q", format="$,.2f")],
    )
    return bars.properties(height=182).configure_view(strokeWidth=0)


def render_overview(result, verification):
    analysis = result["analysis"]
    cases = analysis["scenarios"]
    base = cases["base"]
    benchmark = "Reference" if result["mode"] == "demo" else "Market close"

    quality = render_quality_notice(result)
    render_data_dates(result)
    if quality["state"] in ("low_confidence", "unsuitable"):
        with st.expander("Underlying model calculation"):
            st.caption(f"Computed Base DCF per share: **{usd(base['intrinsic_per_share_usd'])}** "
                       f"(mechanical result; see the concerns above).")
            st.caption("The full scenario table below shows the raw model output for transparency.")

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
    def _gap(case):
        if (cases[case].get("intrinsic_per_share_usd") or 0) < 0:
            return "N/A"  # negative equity → downside % would exceed 100%
        upside = cases[case].get("upside_vs_price_pct")
        return f"{upside:+.1f}%" if upside is not None else "N/A"
    st.dataframe(pd.DataFrame([
        {"Scenario": case.title(), "DCF / share": valuation_display(cases[case]["intrinsic_per_share_usd"]),
         "Gap to price": _gap(case), "WACC": pct(cases[case]["wacc"]),
         "FCFF growth": pct(cases[case]["growth"]) if cases[case].get("growth") is not None else "Driver-based",
         "Terminal growth": pct(cases[case]["terminal_growth"])}
        for case in CASES
    ]), hide_index=True, width="stretch")
    negative_cases = [case for case in CASES if (cases[case].get("intrinsic_per_share_usd") or 0) < 0]
    if negative_cases:
        st.caption(
            f"⚠️ {', '.join(negative_cases).title()} modeled equity is negative — a mechanical artifact: "
            "that scenario's discounted cash flows fall below net debt. Equity is a limited-liability "
            "claim and cannot have a negative price; the signed figure is preserved in the raw export only.")

    # Side-by-side: original five-year vs multi-stage DCF (identical inputs).
    multistage = analysis.get("multistage")
    if multistage:
        st.subheader("Five-year vs multi-stage DCF (identical inputs)")
        st.dataframe(pd.DataFrame([
            {"Scenario": case.title(),
             "Five-year DCF": valuation_display(cases[case]["intrinsic_per_share_usd"]),
             "Multi-stage DCF": valuation_display(multistage[case]["intrinsic_per_share_usd"])}
            for case in CASES
        ]), hide_index=True, width="stretch")

    with st.expander("Comparable-company valuation"):
        render_peers(result)


def render_peers(result):
    relative = result.get("relative")
    if not relative:
        from autoval.peers import peer_groups
        groups = peer_groups(result.get("ticker", ""))
        if not groups:
            st.info("Peer valuation unavailable — no peer group is configured for this industry.")
        else:
            st.info("Peer valuation unavailable — insufficient valid comparable companies "
                    "(or a data-provider failure).")
        return
    target = relative["target"]
    from autoval.peers import discover_peers
    discovery = discover_peers(result.get("ticker", ""))
    method = "Automatic (SIC)" if discovery.get("method") == "sic" else "Curated industry groups"
    st.caption(f"Peer-selection method: **{method}** · Industry: {discovery.get('industry') or discovery.get('sic_description') or 'unmapped'}")
    for reason in discovery.get("excluded", [])[:5]:
        st.caption(f"Excluded `{reason['ticker']}` — {reason['reason']}")
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
    render_quality_notice(result)
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
    render_quality_notice(result)
    market_mode = result.get("market_mode", "current")
    if market_mode not in ("current", "saved") and result["mode"] != "demo":
        st.info("Reverse DCF is unavailable — no genuine current market price is available "
                f"(market-data mode: {market_mode}). The forward valuation remains available.")
        return
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


def render_multistage_lab(result):
    from autoval.multistage import multistage_valuation

    st.subheader("Multi-stage DCF")
    st.caption(
        "Years 1–5 explicit driver forecast · years 6–10 gradual transition · year 11+ "
        "ROIC-consistent terminal. The original five-year DCF is unchanged; this is a "
        "separate model. Historical data is fixed — the controls below are user-defined "
        "assumptions, not guidance, and no market price is used to calibrate them.")
    analysis = result["analysis"]
    render_quality_notice(result)
    forecast = analysis.get("forecast")
    if not forecast:
        st.info("Multi-stage DCF requires a driver-based forecast (available for live analysis).")
        return

    from autoval.quality import assess_multistage_quality
    msq = assess_multistage_quality(result)
    if msq["state"] in ("unsuitable", "low_confidence", "unavailable"):
        st.warning(f"**Multi-stage DCF quality: {msq['state'].replace('_', ' ')}** — "
                   "source-data limitations still apply to this model.")
        for reason in msq["data_quality"]:
            st.caption(f"• {reason}")
        for reason in msq["unsuitability"]:
            st.caption(f"• {reason}")
    for reason in msq["model_suitability"]:
        st.info(f"Multi-stage model-risk note: {reason}")
    base = forecast["base"]
    drivers = base["drivers"]
    run_key = f"{result['ticker']}_{result['run_utc']}"
    net_debt = analysis["scenarios"]["base"]["net_debt_usd"]
    shares = result["analysis"].get("diluted_shares") or result["analysis"].get("shares_outstanding")

    st.markdown("**User-defined assumptions**")
    c1, c2, c3, c4 = st.columns(4)
    growth = c1.slider("Revenue growth", -10.0, 30.0, float(drivers["revenue_growth"]) * 100, 0.5,
                       format="%.1f%%", key=f"ms_g_{run_key}") / 100
    margin = c2.slider("Operating margin", 0.0, 60.0, float(drivers["operating_margin"]) * 100, 0.5,
                       format="%.1f%%", key=f"ms_m_{run_key}") / 100
    capex = c3.slider("CapEx intensity", 0.0, 40.0, float(drivers["capex_ratio"]) * 100, 0.5,
                      format="%.1f%%", key=f"ms_cx_{run_key}") / 100
    trans = c4.slider("Transition years", 1, 10, 5, 1, key=f"ms_t_{run_key}")

    c5, c6, c7 = st.columns(3)
    roic = c5.slider("Mature incremental ROIC", 5.0, 30.0, 12.0, 0.5, format="%.1f%%",
                     key=f"ms_roic_{run_key}") / 100
    wacc = c6.slider("WACC", 5.0, 20.0, float(analysis["scenarios"]["base"]["wacc"]) * 100, 0.25,
                     format="%.2f%%", key=f"ms_w_{run_key}") / 100
    tg = c7.slider("Terminal growth", 0.0, 4.0, 2.0, 0.25, format="%.2f%%",
                   key=f"ms_tg_{run_key}") / 100

    if st.button("Reset to original assumptions", key=f"ms_reset_{run_key}"):
        for k in (f"ms_g_{run_key}", f"ms_m_{run_key}", f"ms_cx_{run_key}", f"ms_t_{run_key}",
                  f"ms_roic_{run_key}", f"ms_w_{run_key}", f"ms_tg_{run_key}"):
            st.session_state.pop(k, None)
        st.rerun()

    # Rebuild the base forecast with the user's growth/margin/capex, then multi-stage it.
    adjusted_drivers = dict(drivers)
    adjusted_drivers["revenue_growth"] = growth
    adjusted_drivers["operating_margin"] = margin
    adjusted_drivers["capex_ratio"] = capex
    try:
        rows = project_fcff(base["base_revenue"], base["base_nwc"], 5, **adjusted_drivers)
        adj_forecast = {"base": {"drivers": adjusted_drivers, "rows": rows,
                                 "base_revenue": base["base_revenue"], "base_nwc": base["base_nwc"]}}
        adjusted = multistage_valuation(adj_forecast, wacc, tg, net_debt, shares,
                                        mature_incremental_roic=roic,
                                        transition_years=trans, case="base")
    except ValueError as exc:
        st.warning(f"These assumptions produce an undefined valuation: {exc}")
        return

    original_base = analysis["scenarios"]["base"]["intrinsic_per_share_usd"]
    ms_base = analysis["multistage"]["base"]["intrinsic_per_share_usd"]

    st.markdown("**Original vs multi-stage (base case)**")
    st.table(pd.DataFrame({
        "Model": ["Original five-year DCF", "Multi-stage (defaults)", "Multi-stage (adjusted)"],
        "DCF / share": [usd(original_base), usd(ms_base), usd(adjusted["intrinsic_per_share_usd"])],
        "Terminal weight of EV": [
            f"{analysis['scenarios']['base']['terminal_weight_of_ev']:.0%}",
            f"{analysis['multistage']['base']['terminal_weight_of_ev']:.0%}",
            f"{adjusted['terminal_weight_of_ev']:.0%}"],
        "Terminal reinvestment rate": [
            "—",
            f"{analysis['multistage']['base']['reinvestment_rate_terminal']:.1%}",
            f"{adjusted['reinvestment_rate_terminal']:.1%}"],
    }).set_index("Model"))

    st.markdown("**Mature ROIC sensitivity (base case, default assumptions)**")
    st.caption("Mature incremental ROIC is an assumed parameter (not market-calibrated). "
               "Higher ROIC → lower sustainable reinvestment → higher terminal FCFF.")
    roic_rows = analysis["multistage"].get("roic_sensitivity") or []
    if not roic_rows:
        st.caption("ROIC sensitivity unavailable for this valuation basis.")
    else:
        st.table(pd.DataFrame([
            {"Mature ROIC": f"{r['mature_incremental_roic']:.0%}",
             "Terminal reinvestment rate": f"{r['reinvestment_rate_terminal']:.1%}" if r.get("valid") else "—",
             "DCF / share": usd(r['intrinsic_per_share_usd']) if r.get("valid") else "invalid"}
            for r in roic_rows
        ]).set_index("Mature ROIC"))

    st.markdown("**Annual FCFF (adjusted, USD B)**")
    st.dataframe(pd.DataFrame([
        {"Year": row["year"], "FCFF": f"{row['fcff'] / 1e9:,.2f}"}
        for row in adjusted["explicit_rows"] + adjusted["transition_rows"]
    ]), hide_index=True, width="stretch")
    st.caption(
        f"Explicit reinvestment rate {adjusted['reinvestment_rate_explicit']:.0%} → terminal "
        f"{adjusted['reinvestment_rate_terminal']:.1%} (g/ROIC = {tg:.1%}/{roic:.1%}). "
        f"Terminal FCFF (year {adjusted['terminal']['year']}) = "
        f"NOPAT × (1 − reinvestment rate) = ${adjusted['terminal']['fcff_usd'] / 1e9:,.1f}B.")


def render_financials(result, prices):
    analysis = result["analysis"]
    st.subheader("Projected free cash flow to the firm")
    render_freshness_notice(result)
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
    render_freshness_notice(result)
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

    st.subheader("Financial evidence centre")
    fin = result["provenance"]["financials"]
    evidence = result.get("evidence") or []

    with st.expander("Structured financial evidence (single source of truth)"):
        if evidence:
            st.dataframe(pd.DataFrame([
                {
                    "Metric": e["metric"],
                    "Kind": e["kind"],
                    "Reported": f"{e['reported_value']:,.0f}" if isinstance(e["reported_value"], (int, float)) else "—",
                    "Derived": f"{e['derived_value']:,.4f}" if isinstance(e["derived_value"], float) else (str(e["derived_value"]) if e["derived_value"] is not None else "—"),
                    "Verification": e["verification_status"],
                    "XBRL tag": e["xbrl_tag"] or "—",
                    "Period end": e["period_end"] or "—",
                }
                for e in evidence
            ]), hide_index=True, width="stretch")
        else:
            st.caption("No structured evidence records for this analysis (legacy snapshot).")

    with st.expander("Source-linked financial reconciliation"):
        rec = fin.get("debt_reconciliation") or {}
        if rec:
            st.table(pd.DataFrame({
                "Line item": list(rec.keys()),
                "Value": [f"{v:,.0f}" if isinstance(v, (int, float)) else str(v) for v in rec.values()],
            }).set_index("Line item"))
        sh = fin.get("shares") or {}
        if sh:
            st.caption(f"Shares: {sh.get('value'):,.0f} · tag {sh.get('tag')} · as of {sh.get('end')}")
        fl = fin.get("finance_lease")
        fl_text = f"{fl['value']:,.0f}" if fl else "none reported"
        lease_notes = " · ".join(fin.get("lease_assumptions") or [])
        st.caption(f"Finance-lease liability: {fl_text} · {lease_notes}")
        if fin.get("url"):
            st.link_button("Open SEC company facts", fin["url"])

    wacc = result.get("wacc") or {}
    with st.expander("WACC calculation and input provenance"):
        calc = wacc.get("calculation") or {}
        if calc:
            st.write(f"WACC **{calc.get('wacc', 0):.2%}** = "
                     f"cost of equity {calc.get('cost_of_equity', 0):.2%} · "
                     f"after-tax cost of debt {calc.get('after_tax_cost_of_debt', 0):.2%}")
            st.write(f"Risk-free {calc.get('risk_free_rate', 0):.2%} · beta {calc.get('beta', 0):.2f} · "
                     f"ERP {calc.get('equity_risk_premium', 0):.2%} · tax {calc.get('marginal_tax_rate', 0):.0%}")
        for key, inp in (wacc.get("inputs") or {}).items():
            src = inp.get("source") or inp.get("period") or "—"
            st.caption(f"{key}: {inp.get('value')} · {src}")

    forecast = result["analysis"].get("forecast") or {}
    base_fc = forecast.get("base") or {}
    drivers = base_fc.get("drivers") or {}
    if drivers:
        with st.expander("FCFF forecast formulas (base drivers)"):
            st.latex(r"\mathrm{Revenue}_t = \mathrm{Revenue}_{t-1}(1+g),\quad "
                     r"\mathrm{NOPAT}_t = \mathrm{Revenue}_t\cdot m\,(1-t)")
            st.latex(r"\mathrm{FCFF}_t = \mathrm{NOPAT}_t + \mathrm{D\&A}_t - \mathrm{CapEx}_t - \Delta\mathrm{NWC}_t")
            st.table(pd.DataFrame({
                "Driver": ["Revenue growth", "Operating margin", "Tax", "D&A / revenue", "CapEx / revenue", "NWC / revenue"],
                "Value": [f"{drivers.get('revenue_growth', 0):.2%}", f"{drivers.get('operating_margin', 0):.2%}",
                          f"{drivers.get('normalized_tax_rate', 0):.0%}", f"{drivers.get('da_ratio', 0):.2%}",
                          f"{drivers.get('capex_ratio', 0):.2%}", f"{drivers.get('nwc_ratio', 0):.2%}"],
            }).set_index("Driver"))

    bridge = result["analysis"].get("bridge")
    if bridge:
        with st.expander("Enterprise-to-equity bridge"):
            st.write(f"Operating EV **${bridge.get('operating_enterprise_value_usd', 0):,.0f}** − "
                     f"total debt ${bridge.get('total_debt_usd', 0):,.0f} + "
                     f"cash ${bridge.get('cash_and_equivalents_usd', 0):,.0f} "
                     f"= equity ${bridge.get('equity_value_usd', {}).get('conservative', 0):,.0f}")

    st.subheader("Export evidence")
    st.caption("Exports contain the original report assumptions. Scenario Lab inputs apply to the what-if view.")
    name = f"autoval_{result['ticker'].lower()}_{result['mode']}"
    report, analysis, check = st.columns(3)
    report.download_button("Research report", build_report_markdown(result), f"{name}.md", "text/markdown", width="stretch")
    analysis.download_button("Analysis JSON", json.dumps(result, indent=2), f"{name}.json", "application/json", width="stretch")
    check.download_button("Verification JSON", json.dumps(verification, indent=2), f"{name}_verification.json", "application/json", width="stretch")
    evidence = result.get("evidence") or []
    if evidence:
        st.download_button("Financial evidence CSV",
                           pd.DataFrame(evidence).to_csv(index=False),
                           f"{name}_evidence.csv", "text/csv", width="stretch")

    # Professional Excel + PDF exports (deterministic, no LLM).
    try:
        from autoval.exports import build_excel_workbook, build_pdf_report
        import tempfile
        import io
        _xlsx = io.BytesIO(); _pdf = io.BytesIO()
        with tempfile.TemporaryDirectory() as td:
            _xp = os.path.join(td, "model.xlsx"); _pp = os.path.join(td, "report.pdf")
            build_excel_workbook(result, _xp); build_pdf_report(result, _pp)
            _xlsx.write(open(_xp, "rb").read()); _pdf.write(open(_pp, "rb").read())
        xlsx_col, pdf_col = st.columns(2)
        xlsx_col.download_button("Excel valuation workbook", _xlsx.getvalue(),
                                 f"{name}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        pdf_col.download_button("PDF research report", _pdf.getvalue(),
                                f"{name}.pdf", "application/pdf", width="stretch")
    except Exception:
        pass  # openpyxl/reportlab optional


def render_reconciliation(result):
    """AI Financial Reconciliation section inside the Financial Evidence Centre.

    Detects reconciliation issues, runs the agent on demand, shows the validated proposal
    and its original evidence, and requires explicit approval before applying a correction
    to a separate snapshot. Fails gracefully when the LLM or SEC provider is unavailable.
    """
    from autoval.reconciliation import detect_issues, investigate, apply_correction, extraction_from_result
    from autoval.reconciliation import llm as recon_llm

    st.caption(
        "Investigate missing, stale or conflicting financial inputs against original SEC "
        "filings. The AI only *proposes* corrections; every proposal is deterministically "
        "validated and requires explicit approval before it is applied to a separate snapshot.")

    ext = extraction_from_result(result)
    try:
        issues = detect_issues(ext)
    except Exception:
        issues = []

    if not issues:
        st.info("No reconciliation issues detected for this analysis.")
        return

    llm_ready = recon_llm.is_configured()
    user_agent = st.session_state.get("sec_contact_email") or os.environ.get("SEC_USER_AGENT", "")
    if not llm_ready:
        st.warning("LLM API is not configured (`AUTOVAL_LLM_API_KEY`). Investigation is unavailable; "
                   "the detected issues are shown below for manual review.")

    proposals = st.session_state.setdefault("recon_proposals", {})

    for issue in issues:
        iid = issue["issue_id"]
        with st.container(border=True):
            st.markdown(f"**Detected issue** · `{issue['category']}`")
            st.write(issue["summary"])
            st.caption(f"Severity: {issue['severity']}")

            col_inv, _ = st.columns([1, 3])
            if col_inv.button("Investigate", key=f"recon_inv_{iid}", disabled=not llm_ready):
                with st.spinner(f"Retrieving SEC filings and investigating {iid}…"):
                    try:
                        proposals[iid] = investigate(ext, user_agent, issue=issue)
                    except Exception as exc:
                        st.error(f"Investigation failed (SEC or LLM unavailable): {exc}")

            if iid not in proposals:
                continue
            p = proposals[iid]
            _render_reconciliation_proposal(p, ext, iid)


def _render_reconciliation_proposal(p, ext, iid):
    v = p.get("deterministic_validation") or {}
    status = v.get("status", "unresolved")
    if status == "validated":
        st.success("Deterministic validation: **validated**")
    elif status == "rejected":
        st.error(f"Deterministic validation: **rejected** — {', '.join(v.get('hard_failures', []) or [])}")
    else:
        st.warning(f"Deterministic validation: **unresolved** — {', '.join(v.get('soft_warnings', []) or [])}")

    orig = p.get("original_production_value")
    prop = p.get("proposed_financial_value")
    st.write(f"Original value: **{orig if orig is not None else 'unavailable'}** → "
             f"Proposed value: **{prop if prop is not None else 'unavailable'}**")
    st.write(f"Financial definition: {p.get('financial_definition')}")
    st.write(f"Derivation formula: `{p.get('derivation_formula')}`")
    st.caption(f"Note / statement reference: {p.get('statement_or_note_reference')}")
    st.caption(f"Filing: {p.get('sec_accession')} · {p.get('filing_url')}")
    if p.get("accounting_explanation"):
        with st.expander("Accounting explanation"):
            st.write(p["accounting_explanation"])
    if p.get("remaining_uncertainty"):
        st.caption(f"Remaining uncertainty: {p['remaining_uncertainty']}")
    tags = p.get("xbrl_tags") or []
    if tags:
        with st.expander(f"XBRL tags and component values ({len(tags)})"):
            st.dataframe(pd.DataFrame(tags), hide_index=True, width="stretch")

    # Approval controls.
    approval = p.get("approval_status")
    if approval == "approved":
        st.success("Approved — correction applied to a separate snapshot.")
        try:
            out = apply_correction(ext, p)
            imp = out["impact"]
            d = imp.get("net_debt_delta")
            ps = imp.get("per_share_impact_usd")
            st.write(f"Net-debt impact: {imp.get('original_net_debt')} → {imp.get('corrected_net_debt')} "
                     f"(Δ {d:+,.0f})" if d is not None else "Net-debt impact: not computable.")
            if ps is not None:
                st.caption(f"Estimated per-share equity impact (net-debt ÷ shares): {ps:+,.2f} USD")
        except Exception as exc:
            st.caption(f"Impact not computable: {exc}")
    elif approval == "rejected":
        st.error("Rejected by user — the original analysis is preserved unchanged.")
    else:
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("Approve", key=f"recon_appr_{iid}"):
            p["approval_status"] = "approved"
            st.rerun()
        if c2.button("Reject", key=f"recon_rej_{iid}"):
            p["approval_status"] = "rejected"
            st.rerun()


def render_reconciliation_workspace(result):
    """Dedicated AI Financial Reconciliation workspace (live + cached case studies)."""
    st.subheader("AI Financial Reconciliation")
    st.caption("Detect and investigate missing/stale/conflicting financial inputs; validated "
               "corrections require explicit approval and apply only to a separate snapshot.")
    render_reconciliation(result)
    st.markdown("---")
    st.subheader("Historical case studies (replayed, labelled)")
    st.caption("These replay previously recorded investigations. They are demonstrations — "
               "distinguish AI-assisted proposals from deterministic engineering fixes.")
    _render_reconciliation_case_studies()


def _render_reconciliation_case_studies():
    import json
    from pathlib import Path
    rec_dir = ROOT / "evidence" / "reconciliation_records"
    if not rec_dir.is_dir():
        st.info("No recorded reconciliation case studies are bundled.")
        return
    tickers = ["WMT", "ORCL", "PG", "UPS"]
    choice = st.selectbox("Case study", tickers, key="recon_case_ui")
    files = sorted(rec_dir.glob(f"{choice}_*.json"))
    if not files:
        st.info(f"No recorded case for {choice}.")
        return
    d = json.load(open(files[-1], encoding="utf-8"))
    v = (d.get("deterministic_validation") or {}).get("status")
    st.markdown(f"**{choice} — recorded case study** (replayed, not recomputed)")
    st.write(f"Issue: {d.get('detected_problem')}")
    st.write(f"Category: `{d.get('category')}` · Validation: **{v}** · Approval: {d.get('approval_status')}")
    if d.get("original_production_value") is not None:
        st.write(f"Original {_fmt_billions(d.get('original_production_value'))} → "
                 f"Proposed {_fmt_billions(d.get('proposed_financial_value'))}")
    if d.get("derivation_formula"):
        st.caption(f"Formula: `{d.get('derivation_formula')}`")
    if d.get("accounting_explanation"):
        with st.expander("Accounting explanation"):
            st.write(d["accounting_explanation"])
    if (d.get("before_after_impact") or {}).get("net_debt_delta") is not None:
        imp = d["before_after_impact"]
        ps = imp.get("per_share_impact_usd")
        ps_txt = f"{ps:+,.2f}" if ps is not None else "—"
        st.write(f"Before/after net-debt Δ: {_fmt_billions(imp.get('net_debt_delta'))} · "
                 f"per-share {ps_txt}")


def _fmt_billions(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9:
        return f"${v/1e9:,.1f}B"
    if a >= 1e6:
        return f"${v/1e6:,.0f}M"
    return f"${v:,.0f}"


def render_research(result):
    """AI Research Analyst tab (read-only, cached, on-demand)."""
    from autoval.research import build_report, deterministic_answer, _FINANCIAL_QUESTIONS, research_cache_key
    from autoval.reconciliation import llm as recon_llm

    st.subheader("AI Research Analyst")
    st.caption(
        "Generates an evidence-grounded research report from this validated analysis snapshot. "
        "Financial tables are rendered deterministically; the AI writes the narrative only. "
        "The report is read-only and never modifies financial inputs or records.")

    # Deterministic financial question interface (works in public mode, no LLM).
    st.markdown("**Ask about this company's financials** (deterministic, source-grounded)")
    q_choice = st.selectbox("Question", _FINANCIAL_QUESTIONS, format_func=lambda s: s.replace("_", " ").title(),
                            key="fin_question_ui")
    ans = deterministic_answer(q_choice, result)
    if ans.get("answer"):
        st.info(ans["answer"])
    else:
        st.caption("No deterministic answer available for this question.")
    st.caption("These answers are computed deterministically from the selected snapshot, "
               "not newly generated AI responses.")

    llm_ready = recon_llm.is_configured()
    if not llm_ready:
        st.warning("Live AI report generation requires an API key (not configured). "
                   "A cached AI research demonstration is shown below.")
        _render_cached_research_demo(result)
        return

    # Private free-text financial question (explicit submit only; grounded + validated).
    st.markdown("**Ask a free-form question** (authorized private mode)")
    question = st.text_input("Question", key="research_question_ui",
                             placeholder="e.g. Why is CapEx so high relative to revenue?")
    if st.button("Ask", key="research_ask_ui"):
        if not question.strip():
            st.warning("Enter a question.")
        else:
            from autoval.research import answer_question
            qcache = st.session_state.setdefault("research_qcache", {})
            _qident = _json.dumps(research_cache_key(result), sort_keys=True, default=str)
            qkey = f"q_{hashlib.sha1((question + _qident).encode()).hexdigest()[:16]}"
            with st.spinner("Answering…"):
                try:
                    ans = answer_question(result, question)
                    qcache[qkey] = ans
                except Exception as exc:
                    st.error(f"Answer failed: {exc}")
            if qkey in qcache:
                a = qcache[qkey]
                if a.get("error"):
                    st.error(a["error"])
                elif a.get("answer"):
                    st.write(a["answer"])
                    v = a.get("validation", {})
                    if v.get("status") == "validated":
                        st.success("Answer claims validated against evidence.")
                    elif v.get("status") == "rejected":
                        st.error("Answer contains unsupported claims: " + "; ".join(v.get("mismatches", [])))
                    if a.get("sources"):
                        st.caption("Sources: " + ", ".join(f"`{s}`" for s in a["sources"]))

    run_key = result.get("run_utc")
    basis = result.get("valuation_basis", "annual")
    import hashlib, json as _json
    from autoval.research import PROMPT_VERSION, MODEL_VERSION
    _ident = _json.dumps(research_cache_key(result), sort_keys=True, default=str)
    cache_key = f"research_{hashlib.sha1(_ident.encode()).hexdigest()[:16]}"
    cache = st.session_state.setdefault("research_cache", {})

    col_gen, _ = st.columns([1, 3])
    if col_gen.button("Generate research report", key=f"gen_{cache_key}", disabled=not llm_ready):
        if cache_key in cache:
            st.info("Report already generated for this snapshot (cached).")
        else:
            with st.spinner("Generating research report…"):
                try:
                    report = build_report(result)
                    cache[cache_key] = report
                except Exception as exc:
                    st.error(f"Report generation failed (LLM unavailable): {exc}")

    report = cache.get(cache_key)
    if not report:
        return

    v = report.get("validation") or {}
    if v.get("status") == "validated":
        st.success("Report validated — evidence citations and snapshot identity verified.")
    else:
        st.error(f"Report validation: {v.get('status')} — "
                 + "; ".join(c["reason"] for c in v.get("checks", []) if not c["ok"]))

    sections = report.get("sections") or {}
    if isinstance(sections, dict) and "error" in sections:
        st.error(sections["error"])
        return

    order = [("executive_summary", "Executive summary"),
             ("business_and_financial_performance", "Business and financial performance"),
             ("revenue_growth_profitability_reinvestment", "Revenue growth, profitability and reinvestment"),
             ("dcf_interpretation", "Five-year vs multi-stage DCF"),
             ("wacc_and_terminal_assumptions", "WACC and terminal-value assumptions"),
             ("comparable_and_reverse_dcf", "Comparable valuation and reverse DCF"),
             ("valuation_drivers_and_sensitivities", "Key valuation drivers and sensitivities"),
             ("risks_and_limitations", "Financial risks and model limitations"),
             ("evidence_backed_conclusion", "Research conclusion")]
    for key, label in order:
        body = sections.get(key)
        if body:
            with st.expander(label, expanded=(key == "executive_summary")):
                st.markdown(str(body))

    st.markdown(report.get("tables", ""))
    st.caption("Financial tables above are rendered deterministically from the snapshot, "
               "not reproduced by the AI.")

    if report.get("evidence_ids"):
        with st.expander("Source evidence (clickable)"):
            fin = (result.get("provenance") or {}).get("financials") or {}
            if fin.get("url"):
                st.link_button("Open SEC company facts", fin["url"])
            st.caption("Evidence IDs cited: " + ", ".join(f"`{i}`" for i in report["evidence_ids"]))

    name = f"autoval_{result['ticker'].lower()}_research_report"
    st.download_button("Download research report (Markdown)", report.get("markdown", ""),
                       f"{name}.md", "text/markdown", width="stretch")

    render_evidence_forecast(result)


def render_evidence_forecast(result):
    """Evidence-backed forecast assumptions (investigate -> validate -> approve -> apply)."""
    from autoval.forecast_assumptions import (
        investigate_assumptions, validate_assumptions, apply_assumptions, _current_drivers)
    from autoval.reconciliation import llm as recon_llm

    def fmt(v):
        if isinstance(v, (int, float)) and 0 <= v < 1:
            return f"{v:.1%}"
        return str(v)

    st.markdown("---")
    st.subheader("Evidence-backed Forecast")
    st.caption("Investigate management guidance / MD&A to propose forecast assumptions. "
               "Approved assumptions regenerate the DCF deterministically; WACC, terminal "
               "growth and mature ROIC are preserved unless separately approved.")

    llm_ready = recon_llm.is_configured()
    current = _current_drivers(result)
    cache = st.session_state.setdefault("forecast_cache", {})
    run_key = f"{result['ticker']}_{result.get('run_utc')}"

    col_inv, _ = st.columns([1, 3])
    if col_inv.button("Investigate forecast assumptions", key=f"fc_inv_{run_key}", disabled=not llm_ready):
        if run_key in cache:
            st.info("Already investigated for this snapshot (cached).")
        else:
            with st.spinner("Retrieving guidance and MD&A…"):
                try:
                    cache[run_key] = investigate_assumptions(result,
                        st.session_state.get("sec_contact_email") or os.environ.get("SEC_USER_AGENT", ""))
                except Exception as exc:
                    st.error(f"Investigation failed: {exc}")

    inv = cache.get(run_key)
    if not inv:
        st.caption("Current (historical-driver) assumptions: "
                   + ", ".join(f"{k} {fmt(current[k])}" for k in current))
        return

    proposals = inv.get("proposals") or []
    if not proposals:
        st.info("No evidence-backed proposals were produced.")
        return

    approval = st.session_state.setdefault("forecast_approvals", {})
    validation = validate_assumptions(proposals, result)
    if validation["status"] == "validated":
        st.success("Proposals validated.")
    else:
        st.error("Proposals rejected: " + "; ".join(c["reason"] for c in validation["checks"] if not c["ok"]))

    for i, p in enumerate(proposals):
        with st.container(border=True):
            st.markdown(f"**{p['driver']}** · original {fmt(p.get("original"))} → "
                        f"proposed {p.get('proposed')} ({p.get('kind')})")
            st.caption(f"Source: {p.get('source')} · {p.get('filing_date')} · {p.get('justification')}")
            st.caption(f"Horizon: {p.get('horizon')} · Uncertainty: {p.get('uncertainty')}")
            key = f"fc_appr_{run_key}_{i}"
            if approval.get(key) == "approved":
                st.success("Approved.")
            else:
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"fc_yes_{run_key}_{i}"):
                    approval[key] = "approved"
                    st.rerun()
                if c2.button("Reject", key=f"fc_no_{run_key}_{i}"):
                    proposals[i] = None
                    st.rerun()

    approved = [p for p in proposals if p is not None and
                approval.get(f"fc_appr_{run_key}_{proposals.index(p)}") == "approved"]
    if approved:
        out = apply_assumptions(result, approved)
        if out.get("status") == "applied":
            st.markdown("**Original vs adjusted DCF**")
            st.table(pd.DataFrame({
                "Scenario": ["Bear", "Base", "Bull"],
                "Original": [fmt(out["before"][c]) for c in ("bear", "base", "bull")],
                "Adjusted": [fmt(out["after"][c]) for c in ("bear", "base", "bull")],
            }).set_index("Scenario"))
            st.caption("WACC, terminal growth and mature ROIC preserved unless separately approved.")


def _render_cached_research_demo(result):
    """Show a cached AI research report (no API key required) for the demo companies."""
    from pathlib import Path
    ticker = (result.get("ticker") or "").lower()
    # exact-match active report only (no cross-company fallback)
    exact = [f"research_report_{ticker}.md"]
    found = None
    for name in exact:
        p = ROOT / "evidence" / name
        if p.exists():
            found = p
            break
    if found:
        st.info(f"Cached AI research (matching snapshot): `{found.name}`")
        with st.expander("Cached AI research report (Markdown)"):
            st.markdown(found.read_text(encoding="utf-8"))
        return
    # no exact match -> separate, clearly-labelled historical library
    evid = ROOT / "evidence"
    library = sorted(evid.glob("research_report_*.md"))
    if not library:
        st.info("No cached AI research report is available for this company.")
        return
    choice = st.selectbox("Historical research library", [p.name for p in library],
                          key="research_library_ui")
    st.warning("This is a separate historical case study — it may belong to a different "
               "company and does NOT represent this analysis.")
    with st.expander(f"Historical report: {choice}"):
        st.markdown((evid / choice).read_text(encoding="utf-8"))


def render_industry_peers(result):
    """Dedicated Industry & Peers workspace (automatic peer discovery + relative valuation)."""
    from autoval.peers import discover_peers, peer_groups
    st.subheader("Industry & Peers")
    ticker = result.get("ticker", "")
    discovery = discover_peers(ticker)
    method = "Automatic (SEC SIC)" if discovery.get("method") == "sic" else (
        "Curated industry groups" if discovery.get("method") == "curated" else "unavailable")
    sic = discovery.get("sic")
    sic_desc = discovery.get("sic_description")
    st.caption(f"Selection method: **{method}** · Industry: {discovery.get('industry') or 'unmapped'} · "
               f"SIC {sic or '—'} {sic_desc or ''}")

    for reason in discovery.get("excluded", [])[:8]:
        st.caption(f"Excluded `{reason['ticker']}` — {reason['reason']}")

    groups = discovery.get("groups", {})
    if not groups:
        st.info("No peer group could be discovered for this company.")
        return

    # Peer selection with user-controlled exclusions.
    excluded = st.session_state.setdefault("peer_exclusions", {})
    for gkey, g in groups.items():
        st.markdown(f"**{g.get('label', gkey)}** — {g.get('rationale', '')}")
        tickers = g.get("tickers", [])
        keep = [t for t in tickers if not excluded.get(f"{gkey}:{t}")]
        cols = st.columns(min(len(tickers), 4) or 1)
        for i, t in enumerate(tickers):
            with cols[i % len(cols)]:
                if st.checkbox(t, value=not excluded.get(f"{gkey}:{t}"), key=f"peer_{gkey}_{t}"):
                    excluded.pop(f"{gkey}:{t}", None)
                else:
                    excluded[f"{gkey}:{t}"] = True
        st.caption(f"Selected peers: {', '.join(keep) or '(none)'}")

    # Relative valuation (live results) or a clear availability note.
    relative = result.get("relative")
    if relative:
        st.subheader("Relative valuation")
        for gkey, gdata in relative.get("groups", {}).items():
            pe = gdata.get("pe", {}); ev = gdata.get("ev_ebitda", {})
            n = gdata.get("sample_size", 0)
            st.caption(f"{gkey.replace('_', ' ').title()} · {n} peers · "
                       f"P/E median {multiple(pe.get('median_pe'))} (P25 {multiple(pe.get('p25_pe'))}, "
                       f"P75 {multiple(pe.get('p75_pe'))}) → implied {usd(pe.get('implied_price_median'))} · "
                       f"EV/EBITDA median {multiple(ev.get('median_ev_ebitda'))} → implied {usd(ev.get('implied_price_median'))}")
            if gdata.get("peers"):
                st.dataframe(pd.DataFrame([
                    {"Peer": p.get("ticker"), "P/E": multiple(p.get("pe")),
                     "EV/EBITDA": multiple(p.get("ev_ebitda")),
                     "Market cap": _fmt_abs(p.get("market_cap")),
                     "Close date": p.get("price_date"), "Notes": p.get("reason")}
                    for p in gdata["peers"]]), hide_index=True, width="stretch")
    else:
        st.info("Live peer multiples require running a live analysis (SEC + market data). "
                "Peer discovery and grouping are shown above from source classification.")


def _fmt_abs(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9:
        return f"${v/1e9:,.1f}B"
    if a >= 1e6:
        return f"${v/1e6:,.0f}M"
    return f"${v:,.0f}"


def render_market_data(result, prices):
    """Dedicated Market Data workspace (historical price + statistics)."""
    import numpy as np
    st.subheader("Market Data")
    mode = result.get("market_mode", "current")
    if mode not in ("current", "saved") or result.get("mode") == "demo":
        st.info(f"Price history shown here is **{mode if mode != 'current' else 'synthetic/demo'}** "
                "data (clearly labelled), not a genuine company price series.")

    if prices is None or prices.empty or "close" not in prices:
        st.info("No price history is available for this analysis.")
        return

    period = st.radio("Period", ("1M", "3M", "6M", "1Y", "5Y"), horizontal=True, index=3)
    days = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252, "5Y": 1260}[period]
    df = prices.tail(days)

    st.caption(f"Closing price + SMA (last {period}) · {len(df)} observations · "
               f"basis: {result.get('market_mode', 'current')}")
    st.line_chart(df[["close", "sma20", "sma50", "sma200"]] if "sma20" in df else df[["close"]],
                  height=260)

    close = df["close"].dropna()
    if len(close) >= 2:
        ret = close.iloc[-1] / close.iloc[0] - 1
        daily = close.pct_change().dropna()
        vol = float(np.std(daily, ddof=1)) * np.sqrt(252) if len(daily) > 1 else None
        peak = close.cummax()
        dd = (close / peak - 1).min()
        c1, c2, c3 = st.columns(3)
        c1.metric("Period return", f"{ret:+.1%}")
        c2.metric("Annualized volatility", f"{vol:.1%}" if vol is not None else "—")
        c3.metric("Maximum drawdown", f"{dd:.1%}")
    st.caption("SMA/return/volatility/drawdown are computed from the series above. "
               "Synthetic series are illustrative backtests, not actual company performance.")
    if result.get("mode") == "demo":
        st.caption("⚠️ This is a synthetic demo series (ends at the displayed close); "
                   "it is NOT genuine historical market data.")


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

    def quality_label(state):
        return {"available": "Available",
                "low_confidence": "Low confidence",
                "unsuitable": "Model review required",
                "unavailable": "Unavailable",
                "not_assessed": "Not assessed"}.get(state, "Not assessed")

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
            quality_label(row["quality_state"]),
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
    for row in rows:
        if row["quality_state"] in ("low_confidence", "unsuitable", "unavailable") and row["quality_reasons"]:
            st.warning(f"{row['ticker']}: {row['quality_reasons']}")
    labels = [
        "Company", "Data mode", "Currency", "Reference or close price", "Price date", "Fiscal period end",
        "Base DCF per share", "Valuation gap (USD)", "Valuation gap (%)",
        "Base WACC", "WACC basis", "Base forecast growth",
        "Forecast growth measure", "Price-implied FCFF growth", "Peer group",
        "Valued peers", "Median P/E", "Median EV/EBITDA", "Valuation quality",
    ]
    headers = [str(row["ticker"]) for row in rows]
    if headers[0] == headers[1]:
        headers = [f"{ticker} ({index})" for index, ticker in enumerate(headers, start=1)]
    st.table(pd.DataFrame({"Metric": labels, headers[0]: first, headers[1]: second}).set_index("Metric"))
    st.caption("Valuation gap = (base DCF per share ÷ reference or close price − 1) × 100.")
    st.download_button("Download comparison CSV", csv_data, "autoval_comparison.csv", "text/csv")


def main():
    # Unconditional public-demo protection at the entrypoint: the paid LLM is prohibited by
    # default (no Streamlit secrets or run_demo.sh required). Only an explicit
    # AUTOVAL_PRIVATE_MODE=1 (authorized private workspace) enables live AI.
    if os.environ.get("AUTOVAL_PRIVATE_MODE") != "1":
        os.environ["AUTOVAL_PUBLIC_DEMO"] = "1"
        os.environ["AUTOVAL_LLM_USE_RUNTIME_CONFIG"] = "0"
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
    has_ttm = result["analysis"].get("ttm") is not None
    basis_label = st.radio(
        "Valuation basis", ("Latest TTM", "Annual"), horizontal=True,
        key="valuation_basis_ui", disabled=not has_ttm,
        help="TTM uses the latest trailing-twelve-month operating results; Annual uses the completed fiscal year.")
    result = apply_basis(result, "ttm" if basis_label == "Latest TTM" and has_ttm else "annual")
    failed = st.session_state.get("failed_ticker")
    if failed and failed != result["ticker"]:
        st.warning(f"The analysis requested for **{failed}** did not complete. "
                   f"The report below is the last successful analysis for **{result['ticker']}** — "
                   f"it is not a result for **{failed}**.")
    verification = check_report(result)
    overview_header(result)
    overview, lab, multistage, expectations, financials, evidence, research, recon, peers, market = st.tabs(
        ["Overview", "Scenario Lab", "Multi-stage DCF", "Market Expectations", "Financials",
         "Evidence & Exports", "AI Research Analyst", "AI Reconciliation", "Industry & Peers", "Market Data"],
    )
    with overview:
        render_overview(result, verification)
    with lab:
        render_scenario_lab(result)
    with multistage:
        render_multistage_lab(result)
    with expectations:
        render_market_expectations(result)
    with financials:
        render_financials(result, prices)
    with evidence:
        render_evidence(result, verification)
    with research:
        render_research(result)
    with recon:
        render_reconciliation_workspace(result)
    with peers:
        render_industry_peers(result)
    with market:
        render_market_data(result, prices)
    st.caption("Educational research prototype for U.S. nonfinancial SEC filers.")


if __name__ == "__main__":
    main()
