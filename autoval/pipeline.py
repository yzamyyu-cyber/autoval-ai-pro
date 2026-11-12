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

ROOT = Path(__file__).resolve().parent.parent


def demo_market_closes() -> pd.Series:
    # Deterministic, explicitly synthetic series. Does not imply real trading behavior.
    ix = pd.bdate_range(end="2026-10-30", periods=320)
    dates = np.arange(len(ix))
    raw = (1.0012 ** dates) * (1 + .045 * np.sin(dates/13.0))
    close = 145.0 * raw / raw[-1]
    return pd.Series(close, index=ix, name="close")


def build_analysis(ticker: str = "DEMO", mode: str = "demo", user_agent: str = "") -> tuple[dict,pd.DataFrame]:
    ticker = ticker.upper().strip()
    if not ticker.isalnum() or len(ticker) > 10:
        raise ValueError("Ticker must be 1-10 letters/numbers; avoid arbitrary URLs or command input")
    if mode == "demo":
        with (ROOT / "examples" / "demo_company.json").open(encoding="utf-8") as f:
            stock = json.load(f)
        if ticker != "DEMO":
            raise ValueError("Offline example is only available for ticker DEMO; choose Live for other tickers")
        closes = demo_market_closes()
        market_source = {"provider": "Synthetic deterministic series", "realtime": False,
                         "price_basis": "Separate illustrative market price in demo_company.json",
                         "backtest_basis": "Synthetic generated prices"}
    elif mode == "live":
        from .sec import get_sec_financials
        market = fetch_market(ticker)
        stock = get_sec_financials(ticker, user_agent)
        stock["market_price"] = market["market_price"]
        stock["price_date"] = market["price_date"]
        closes = market["close_prices"]
        market_source = market["market_source"]
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
    df, indicators = analyze_technical(closes)

    # Relative valuation (live mode, best-effort; peers retrieved automatically).
    relative = None
    if mode == "live":
        try:
            from .peers import peer_groups
            from .relative_data import build_relative_valuation
            from .relative import summarize_relative_valuation
            pgroups = peer_groups(ticker)
            if pgroups:
                rel = build_relative_valuation(ticker, user_agent, pgroups,
                                               target_price=stock.get("market_price"),
                                               target_price_date=stock.get("price_date"))
                relative = {
                    "groups": summarize_relative_valuation(rel["target"], rel["peers"], pgroups),
                    "target": rel["target"],
                    "peer_map": pgroups,
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
        "limitations": valuation["limitations"] + extra_limitations,
    }
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
    summary = f'''# AutoVal AI — {result["ticker"]} ({result["mode"]})

> {result["company"]}

Data mode: **{result["mode"]}** · Price as of: {result["analysis"]["price_date"]} · Financial FY: {result["analysis"]["financial_asof"]}

Latest available market close: **${result["analysis"]["market_price"]:,.2f}** per share (not necessarily real-time).

| DCF case | Intrinsic per share (USD) | Upside vs close | WACC | FCFF growth | Terminal g |
|---|---:|---:|---:|---:|---:|
'''
    for case in ("bear","base","bull"):
        r = scenario[case]
        growth_disp = f'{r["growth"]:.1%}' if r.get("growth") is not None else "driver"
        summary += (f'| {case.title()} | ${r["intrinsic_per_share_usd"]:,.2f} | '
                    f'{r["upside_vs_price_pct"]:+.1f}% | {r["wacc"]:.1%} | '
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
