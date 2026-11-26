#!/usr/bin/env python3
"""Cross-company D&A extraction audit.

For each development company, records the selected D&A tag, accounting definition, the
production amount (latest FY), the D&A status (consolidated / derived / unavailable), and
whether the extraction was blocked. Writes a machine-readable matrix.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/da_audit.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import sec_lookup, fetch_json, FACTS_URL
from autoval.da import resolve_annual_da
from autoval.forecast_data import retrieve_history

MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "da_extraction_matrix.json")

TICKERS = ("MSFT", "AMZN", "AAPL", "HD", "GOOGL", "TSLA", "NVDA", "WMT", "COST", "KO",
           "PG", "MCD", "NKE", "XOM", "CAT", "UPS", "JNJ", "DIS", "ORCL", "AMD")


def audit(ticker, ua):
    row = {"ticker": ticker, "status": None, "tag": None, "definition": None,
           "amount": None, "source_amount": None, "difference": None, "verification": None}
    try:
        hist = retrieve_history(ticker, ua)
    except Exception as exc:
        row["status"] = "blocked"
        row["verification"] = f"unavailable ({type(exc).__name__})"
        return row
    row["status"] = hist.get("da_status")
    detail = hist.get("da_detail") or []
    latest = detail[-1] if detail else {}
    row["tag"] = latest.get("tag")
    row["definition"] = ("consolidated D&A" if row["status"] == "consolidated"
                         else ("reconstructed components" if row["status"] == "derived"
                               else "unavailable"))
    row["amount"] = hist["da"][-1] if hist.get("da") else None
    row["verification"] = "source-verified" if row["status"] == "consolidated" else (
        "derived" if row["status"] == "derived" else "unresolved")
    return row


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    matrix = []
    for t in TICKERS:
        try:
            matrix.append(audit(t, ua))
        except Exception as exc:
            matrix.append({"ticker": t, "status": "error", "verification": str(exc)})
    with open(MATRIX, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(matrix, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
