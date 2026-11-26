"""Single entry-point for both demo and ticker-only live prototype modes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import numpy as np
import pandas as pd
from .finance import analyze_valuation, observed_multiples
from .technical import analyze_technical
from .sec import get_sec_financials
from .market import fetch_market
from .market_data import classify_market_data

ROOT = Path(__file__).resolve().parent.parent
DEMO_FILES = {"DEMO": "demo_company.json", "DEMO2": "demo_company_2.json"}


def demo_market_closes(price: float = 145.0, price_date: str = "2026-10-30") -> pd.Series:
    # Deterministic, explicitly synthetic series. Does not imply real trading behavior.
    ix = pd.bdate_range(end=price_date, periods=320)
    dates = np.arange(len(ix))
    raw = (1.0012 ** dates) * (1 + .045 * np.sin(dates/13.0))
    close = price * raw / raw[-1]
    return pd.Series(close, index=ix, name="close")


def build_analysis(ticker: str = "DEMO", mode: str = "demo", user_agent: str = "",
                   *, market_mode: str | None = None, saved_price=None, saved_price_date=None,
                   illustrative_price=None) -> tuple[dict,pd.DataFrame]:
    ticker = ticker.upper().strip()
    if not ticker.isalnum() or len(ticker) > 10:
        raise ValueError("Ticker must be 1-10 letters/numbers; avoid arbitrary URLs or command input")
    if mode == "demo":
        if ticker not in DEMO_FILES:
            raise ValueError("Offline examples are available for DEMO and DEMO2.")
        with (ROOT / "examples" / DEMO_FILES[ticker]).open(encoding="utf-8") as f:
            stock = json.load(f)
        closes = demo_market_closes(stock["market_price"], stock["price_date"])
        market_source = {"provider": "Synthetic deterministic series", "realtime": False,
                         "price_basis": f"Illustrative reference price in {DEMO_FILES[ticker]}",
                         "backtest_basis": "Synthetic generated prices"}
    elif mode == "live":
        from .sec import get_sec_financials
        stock = get_sec_financials(ticker, user_agent)
        from .market_data import resolve_market
        explicit = market_mode if market_mode is not None else os.environ.get("AUTOVAL_MARKET_MODE", "")
        market_source, resolved_mode, closes, price, price_date = resolve_market(
            ticker, explicit, fetch_market,
            saved_price=saved_price, saved_price_date=saved_price_date)
        stock["market_price"] = price
        stock["price_date"] = price_date
        if illustrative_price is not None:
            # Hypothetical reference stored SEPARATELY; never written into market_price.
            stock["illustrative_market_price"] = float(illustrative_price)
    else:
        raise ValueError("Mode must be demo or live")
    # Optional operator-verified note adjustment (NOT required for ticker-only use):
    # the restricted-investments portion classified within short-term investments.
    # When unset, the bridge reports a conservative-to-upper range rather than a point estimate.
    _ris = os.environ.get("RESTRICTED_IN_SHORT_TERM_USD")
    if _ris:
        try:
            stock["restricted_in_short_term"] = float(_ris)
        except ValueError:
            pass

    # Company-specific WACC (live mode only). When unavailable, the valuation falls back
    # to the illustrative WACC and is explicitly labeled as such (not company-specific).
    wacc_block = None
    company_wacc = None
    if mode == "live":
        from .wacc_data import build_company_wacc
        wacc_block = build_company_wacc(ticker, stock, user_agent)
        if wacc_block.get("available"):
            company_wacc = wacc_block["wacc"]

    # Driver-based forecast (v5). Falls back to constant-growth when driver history is unavailable.
    forecast_history = None
    if mode == "live":
        from .forecast_data import retrieve_history
        try:
            forecast_history = retrieve_history(ticker, user_agent)
        except Exception:
            forecast_history = None

    if forecast_history is not None:
        from .finance import analyze_driver_valuation
        valuation = analyze_driver_valuation(stock, forecast_history, company_wacc)
    else:
        valuation = analyze_valuation(stock, company_wacc)
    observed = observed_multiples(stock)
    try:
        df, indicators = analyze_technical(closes)
    except (ValueError, TypeError):
        # No genuine price history (missing / illustrative / dated-saved) -> technical
        # backtest is unavailable but the valuation must not crash.
        df = pd.DataFrame(columns=["close", "sma20", "sma50", "sma200", "signal",
                                   "position", "daily_return", "trade", "strategy_daily_return"])
        indicators = {
            "last_session": None, "sma20": None, "sma50": None, "sma200": None,
            "trend": "unavailable", "latest_signal": "unavailable",
            "comparison_start": None,
            "strategy_total_return_pct": 0.0, "buyhold_total_return_pct": 0.0,
            "cost_bps_per_trade": 10.0, "method": "unavailable",
            "warning": "Technical backtest unavailable: no genuine market price history (201+ closes required).",
        }

    # Relative valuation (live mode, best-effort; peers retrieved automatically).
    relative = None
    if mode == "live":
        try:
            from .peers import discover_peers
            from .relative_data import build_relative_valuation
            from .relative import summarize_relative_valuation
            discovery = discover_peers(ticker, user_agent)
            pgroups = {k: v["tickers"] for k, v in discovery.get("groups", {}).items()}
            if pgroups:
                rel = build_relative_valuation(ticker, user_agent, pgroups,
                                               target_price=stock.get("market_price"),
                                               target_price_date=stock.get("price_date"),
                                               target_market_mode=resolved_mode)
                relative = {
                    "groups": summarize_relative_valuation(rel["target"], rel["peers"], pgroups),
                    "target": rel["target"],
                    "peer_map": pgroups,
                    "discovery": discovery,
                }
        except Exception:
            relative = None

    if not market_source.get("backtest_basis", "").startswith("Adjusted") and mode == "live":
        indicators["data_warning"] = "Raw close used for backtest; splits and dividends may distort returns"
    extra_limitations = [
        "Observed P/E and EV/EBITDA are not peer-based fair value estimates.",
        "Technical backtest is in-sample; past returns do not predict future performance.",
        "Prototype has not been validated for all issuers or publicly deployed.",
    ]
    if mode == "live" and not (wacc_block or {}).get("available"):
        extra_limitations.insert(0, "Company-specific WACC unavailable; intrinsic values use the illustrative (non-company-specific) WACC and are not presented as a company-specific valuation.")
    result = {
        "project": "AutoVal AI Pro | Educational prototype v0.1.0",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "company": stock["company"], "ticker": ticker,
        "analysis": valuation, "technical": indicators,
        "multiples": observed,
        "wacc": wacc_block,
        "forecast_history": forecast_history,
        "forecast_basis": "driver" if forecast_history is not None else "constant_growth",
        "relative": relative,
        "provenance": {"financials":stock["source"], "market":market_source},
        "market_mode": classify_market_data(market_source, stock.get("market_price")),
        "illustrative_market_price": stock.get("illustrative_market_price"),
        "limitations": valuation["limitations"] + extra_limitations,
        "valuation_basis": "ttm" if valuation.get("ttm") is not None else "annual",
        "valuation_basis_asof": (valuation.get("ttm") or {}).get("asof")
                                or valuation.get("financial_asof"),
        "valuation_date": (valuation.get("ttm") or {}).get("asof")
                          or valuation.get("financial_asof"),
    }
    from .quality import assess_valuation_quality
    result["quality"] = assess_valuation_quality(result)
    from .provenance import build_provenance
    result["evidence"] = build_provenance(result)
    # WACC provenance classification: company-specific only when beta and equity value
    # are genuine market observations (not assumed/placeholder).
    from .market_data import classify_wacc
    wi = (wacc_block or {}).get("inputs") or {}
    beta_avail = bool(wi.get("beta", {}).get("available"))
    equity_avail = bool(wi.get("equity_value", {}).get("available"))
    result["wacc_basis"] = classify_wacc(wacc_block, beta_avail, equity_avail)
    # Data freshness (never crashes an otherwise valid analysis).
    cik = (stock.get("source") or {}).get("cik")
    if mode == "live" and cik:
        try:
            from .freshness import check_freshness
            result["freshness"] = check_freshness(cik, user_agent)
        except Exception:
            result["freshness"] = {"status": "unknown"}
    else:
        result["freshness"] = {"status": "offline"}
    return result, df


def save_analysis(result: dict, prices: pd.DataFrame, output: str | Path) -> dict:
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    file_json = out / "analysis.json"
    file_csv = out / "technical.csv"
    file_md = out / "summary.md"
    file_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    prices.to_csv(file_csv, float_format="%.10g")
    forecast = result["analysis"].get("forecast")
    file_fc = None
    if forecast:
        file_fc = out / "forecast.csv"
        frows = []
        for case in ("bear", "base", "bull"):
            for r in forecast[case]["rows"]:
                frows.append({"scenario": case, **r})
        pd.DataFrame(frows).to_csv(file_fc, index=False, float_format="%.6f")
    file_peer = None
    file_rel = None
    if result.get("relative"):
        file_peer = out / "peer_comparison.csv"
        file_rel = out / "relative_valuation.json"
        prow = []
        for gkey, g in result["relative"]["groups"].items():
            for p in g["peers"]:
                prow.append({"group": gkey, **{k: v for k, v in p.items() if k != "peers"}})
        pd.DataFrame(prow).to_csv(file_peer, index=False)
        file_rel.write_text(json.dumps(result["relative"], indent=2, default=str), encoding="utf-8")
    scenario = result["analysis"]["scenarios"]
    price = result["analysis"]["market_price"]
    price_disp = f"${price:,.2f}" if price is not None else "unavailable (no genuine market price)"
    price_date_disp = result["analysis"]["price_date"] or "unavailable"
    summary = f'''# AutoVal AI — {result["ticker"]} ({result["mode"]})

> {result["company"]}

Data mode: **{result["mode"]}** · Market-data mode: **{result.get("market_mode", "current")}** · Price as of: {price_date_disp} · Financial FY: {result["analysis"]["financial_asof"]}

Latest available market close: **{price_disp}** per share (not necessarily real-time).

| DCF case | Intrinsic per share (USD) | Upside vs close | WACC | FCFF growth | Terminal g |
|---|---:|---:|---:|---:|---:|
'''
    for case in ("bear","base","bull"):
        r = scenario[case]
        growth_disp = f'{r["growth"]:.1%}' if r.get("growth") is not None else "driver"
        gap_disp = f'{r["upside_vs_price_pct"]:+.1f}%' if r.get("upside_vs_price_pct") is not None else "n/a"
        summary += (f'| {case.title()} | ${r["intrinsic_per_share_usd"]:,.2f} | '
                    f'{gap_disp} | {r["wacc"]:.1%} | '
                    f'{growth_disp} | {r["terminal_growth"]:.1%} |\n')
    bridge = result["analysis"].get("bridge")
    if bridge:
        eligible = bridge["eligible_nonoperating_securities_usd"]
        econs = eligible.get("conservative")
        eupp = eligible.get("upper")
        erec = eligible.get("reconciled")
        summary += f'''
## Enterprise-to-equity bridge

- Operating enterprise value (base): ${bridge["operating_enterprise_value_usd"]:,.0f}
- Total debt: ${bridge["total_debt_usd"]:,.0f} · Cash: ${bridge["cash_and_equivalents_usd"]:,.0f}
- Short-term investments: ${(bridge["short_term_investments_usd"] or 0):,.0f} · Restricted (total): ${(bridge["restricted_investments_total_usd"] or 0):,.0f}
- Eligible nonoperating securities — conservative: ${econs:,.0f} · upper: ${eupp:,.0f}'''
        if erec is not None:
            summary += f' · reconciled: ${erec:,.0f}'
        summary += "\n- Upper bound is NOT a verified valuation; reconciled case requires note verification.\n"
    summary += f'''
## Technical backtest (illustrative, in-sample)

- SMA20 > SMA50: {result["technical"]["latest_signal"]}
- Strategy: {result["technical"]["strategy_total_return_pct"]:+.2f}%
- Buy-and-hold (same period): {result["technical"]["buyhold_total_return_pct"]:+.2f}%
- Cost: {result["technical"]["cost_bps_per_trade"]} basis points per position change

## Source and caveats

- Financial source: {result["provenance"]["financials"]["provider"]}
- Financial URL: {result["provenance"]["financials"].get("url") or "synthetic example"}
- Market source: {result["provenance"]["market"]["provider"]}
- WACC assumption: {result["analysis"]["assumption_provenance"]["wacc"]}

This output is a reproducible educational model, **not an investment recommendation**. Check `analysis.json` for complete assumptions, dates, source tags and limitations.
'''
    file_md.write_text(summary, encoding="utf-8")
    out_files = {"analysis": str(file_json), "technical": str(file_csv), "summary": str(file_md)}
    if file_fc is not None:
        out_files["forecast"] = str(file_fc)
    if file_peer is not None:
        out_files["peer_comparison"] = str(file_peer)
    if file_rel is not None:
        out_files["relative_valuation"] = str(file_rel)
    return out_files
