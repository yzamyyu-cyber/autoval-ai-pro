#!/usr/bin/env python3
"""Phase 2E — apply existing validated proposals and build the compact acceptance matrix.

Reuses the validated reconciliation records for PG/ORCL/MCD (no new LLM calls), applies them
through apply_correction, and regenerates the valuation by injecting the corrected stock into
the production build_analysis. JNJ is resolved deterministically. Outputs a machine-readable
matrix covering all 20 companies.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/phase2e_acceptance.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.reconciliation import apply_correction, list_records, load_record
from autoval.pipeline import build_analysis
from autoval.forecast_data import retrieve_history

MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recovery_completion_matrix.json")
RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")

TICKERS = ("MSFT", "AMZN", "AAPL", "HD", "GOOGL", "TSLA", "NVDA", "WMT", "COST", "KO",
           "PG", "MCD", "NKE", "XOM", "CAT", "UPS", "JNJ", "DIS", "ORCL", "AMD")


def latest_record(ticker):
    for p in reversed(list_records(RECORDS_DIR)):
        if os.path.basename(p).startswith(ticker + "_"):
            return load_record(p)
    return None


def corrected_valuation(ticker, ua):
    """Apply the validated proposal (if any) and regenerate the valuation."""
    rec = latest_record(ticker)
    v = (rec or {}).get("deterministic_validation", {})
    try:
        stock = get_sec_financials(ticker, ua)
    except Exception as exc:
        return {"ticker": ticker, "extraction": f"blocked ({type(exc).__name__})",
                "ai_status": (v.get("status") if rec else None)}
    if rec and v.get("status") == "validated" and rec.get("proposed_financial_value") is not None:
        corrected = apply_correction(stock, rec)["corrected"]
        result = _rebuild(corrected, ticker, ua)
        return {"ticker": ticker, "extraction": "ok", "ai_status": "applied",
                "original_net_debt": stock.get("net_debt"),
                "corrected_net_debt": corrected.get("net_debt"),
                "base_dcf_per_share": result["analysis"]["scenarios"]["base"]["intrinsic_per_share_usd"],
                "quality": result["quality"]["state"]}
    return {"ticker": ticker, "extraction": "ok" if stock.get("debt_available") else "blocked",
            "ai_status": v.get("status") if rec else "not_reconciled",
            "net_debt": stock.get("net_debt")}


def _rebuild(corrected_stock, ticker, ua):
    import autoval.sec as sec
    orig = sec.get_sec_financials
    sec.get_sec_financials = lambda t, u: corrected_stock
    try:
        result, _ = build_analysis(ticker, "live", ua, market_mode="illustrative",
                                   illustrative_price=100.0)
    finally:
        sec.get_sec_financials = orig
    return result


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    rows = []
    for t in TICKERS:
        try:
            rows.append(corrected_valuation(t, ua))
        except Exception as exc:
            rows.append({"ticker": t, "error": f"{type(exc).__name__}: {exc}"})
    with open(MATRIX, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
