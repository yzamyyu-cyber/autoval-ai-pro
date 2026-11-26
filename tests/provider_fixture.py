"""Test-only data-provider harness.

Loads a deterministic sanitized fixture (stock + forecast history + WACC inputs) and runs
the PRODUCTION valuation (analyze_driver_valuation) on it — no pre-rendered results, no
live network. Produces a complete `build_analysis`-shaped result so the full Streamlit app
can be exercised deterministically for each ticker.
"""
from __future__ import annotations
import json
import os

import pandas as pd

from autoval.finance import analyze_driver_valuation

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def build_from_fixture(ticker: str, market_mode: str = "current"):
    """Return (result, prices) for a ticker from its saved fixture.

    `market_mode` selects the market-data provenance to exercise the four acceptance
    conditions: current / saved (genuine dated price) / illustrative (hypothetical price
    held separately) / missing (no price). The production valuation still runs in every
    mode; only the market price provenance changes.
    """
    with open(os.path.join(FIXTURE_DIR, f"{ticker}.json")) as f:
        fx = json.load(f)

    stock = dict(fx["stock"])
    history = fx["history"]
    wacc = fx["wacc"]
    genuine_price = stock.get("market_price")
    genuine_date = stock.get("price_date")

    if market_mode in ("illustrative", "missing"):
        # No genuine market price. Illustrative stores the hypothetical separately.
        stock["market_price"] = None
        stock["price_date"] = None
    # current/saved keep the genuine (dated) fixture price.

    valuation = analyze_driver_valuation(stock, history, wacc)

    # minimal deterministic technical stub (real indicators are not under test here)
    # Synthetic, clearly-labelled price series that ENDS at the genuine fixture market
    # price (so the historical chart is consistent with the displayed market close). Not
    # presented as genuine market history.
    from autoval.pipeline import demo_market_closes
    close_s = demo_market_closes(genuine_price, genuine_date)
    idx = close_s.index
    prices = pd.DataFrame({
        "close": close_s.values,
        "sma20": close_s.rolling(20, min_periods=1).mean().values,
        "sma50": close_s.rolling(50, min_periods=1).mean().values,
        "sma200": close_s.rolling(200, min_periods=1).mean().values,
    }, index=idx)
    technical = {
        "latest_signal": "Hold", "strategy_total_return_pct": 0.0,
        "buyhold_total_return_pct": 0.0, "cost_bps_per_trade": 10.0,
        "warning": "fixture (deterministic synthetic technical series, ends at the displayed close)",
    }

    ttm_asof = (valuation.get("ttm") or {}).get("asof")
    from autoval.wacc import compute_wacc
    wcalc = compute_wacc(fx["wacc_inputs"]["rf"], fx["wacc_inputs"]["beta"],
                         fx["wacc_inputs"]["erp"], fx["wacc_inputs"]["equity_value"],
                         fx["wacc_inputs"]["debt"],
                         fx["wacc_inputs"]["interest"] / fx["wacc_inputs"]["debt"],
                         fx["wacc_inputs"]["tax"])
    market_source = {
        "current": {"mode": "current", "provider": "fixture (genuine live close)",
                    "price_date": genuine_date, "classification": "current market data"},
        "saved": {"mode": "saved", "provider": "fixture (genuine dated saved snapshot)",
                  "price_date": genuine_date, "classification": "dated saved data"},
        "illustrative": {"mode": "illustrative", "provider": "fixture (explicit illustrative assumptions)",
                         "classification": "illustrative assumptions"},
        "missing": {"mode": "missing", "provider": "fixture (market provider failure)",
                    "classification": "missing market data"},
    }[market_mode]
    wacc_basis = "company-specific" if market_mode in ("current", "saved") else \
        ("illustrative" if market_mode == "illustrative" else "unavailable")
    result = {
        "project": "AutoVal AI Pro | Educational prototype v0.1.0",
        "run_utc": "2026-11-24T00:00:00+00:00",
        "mode": "live",
        "company": stock["company"], "ticker": ticker,
        "analysis": valuation,
        "technical": technical,
        "multiples": {},
        "wacc": {"available": True, "wacc": wacc, "calculation": wcalc,
                 "inputs": {
                     "risk_free_rate": {"value": fx["wacc_inputs"]["rf"], "period": "fixture"},
                     "beta": {"value": fx["wacc_inputs"]["beta"], "period": "fixture"},
                     "equity_risk_premium": {"value": fx["wacc_inputs"]["erp"], "period": "fixture"},
                 }},
        "forecast_history": history,
        "forecast_basis": "driver",
        "relative": None,
        "provenance": {"financials": stock.get("source", {}), "market": market_source},
        "market_mode": market_mode,
        "illustrative_market_price": (genuine_price if market_mode == "illustrative" else None),
        "wacc_basis": wacc_basis,
        "limitations": valuation["limitations"],
        "valuation_basis": "ttm" if valuation.get("ttm") else "annual",
        "valuation_basis_asof": ttm_asof or valuation.get("financial_asof"),
        "valuation_date": ttm_asof or valuation.get("financial_asof"),
    }
    from autoval.quality import assess_valuation_quality
    result["quality"] = assess_valuation_quality(result)
    from autoval.provenance import build_provenance
    result["evidence"] = build_provenance(result)
    # Optional reconciliation-issue injection for the AI-reconciliation UI tests (offline).
    if os.environ.get("AUTOVAL_FIXTURE_RECON_ISSUE"):
        fin = json.loads(json.dumps(result["provenance"]["financials"]))
        fin["excluded_debt_tags"] = [
            {"tag": "CommercialPaper", "status": "stale_nonzero",
             "last_end": "2026-06-30", "last_value": 4_837_000_000}]
        fin["cash"] = {"tag": "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                       "value": 15_365_000_000, "end": "2026-09-30"}
        rec = fin.get("debt_reconciliation") or {}
        rec["reference_date"] = "2026-09-30"
        rec["net_debt"] = None
        rec["total_debt"] = None
        fin["debt_reconciliation"] = rec
        result["provenance"]["financials"] = fin
    # Recorded freshness (NVDA has a newer 8-K Item 2.02 earnings release, per fixture).
    if ticker == "NVDA":
        result["freshness"] = {"status": "newer-results-available",
                               "latest_periodic_filing": "2026-08-26",
                               "latest_periodic_report_date": "2026-07-26",
                               "newer_earnings_release": "2026-11-17",
                               "newer_earnings_report_date": "2026-10-25"}
    else:
        result["freshness"] = {"status": "up-to-date"}
    return result, prices
