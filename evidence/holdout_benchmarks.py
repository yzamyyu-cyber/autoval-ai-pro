#!/usr/bin/env python3
"""Phase 2F — independent financial benchmarks for the five holdout companies.

Extracts reference values (revenue, operating income, D&A, CapEx, cash, debt, leases, shares)
from the original SEC companyfacts and inline XBRL, kept SEPARATE from the agent's inputs.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/holdout_benchmarks.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.forecast_data import retrieve_history

HOLDOUT = ("PFE", "INTC", "DE", "PEP", "CSCO")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdout_benchmarks.json")


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    out = {}
    for t in HOLDOUT:
        try:
            ext = get_sec_financials(t, ua)
            hist = retrieve_history(t, ua)
            rec = (ext.get("source") or {}).get("debt_reconciliation") or {}
            out[t] = {
                "revenue": hist.get("revenue"),
                "operating_income": hist.get("operating_income"),
                "da": hist.get("da"),
                "da_status": hist.get("da_status"),
                "capex": hist.get("capex"),
                "cash_and_equivalents": ext.get("cash_and_equivalents"),
                "total_debt": ext.get("total_debt"),
                "net_debt": ext.get("net_debt"),
                "finance_lease": (rec.get("finance_lease")),
                "shares": ext.get("shares"),
                "diluted_shares": ext.get("diluted_shares"),
                "balance_sheet_asof": ext.get("balance_sheet_asof"),
                "debt_available": ext.get("debt_available"),
                "fiscal_years": hist.get("fiscal_years"),
            }
        except Exception as exc:
            out[t] = {"error": f"{type(exc).__name__}: {exc}"}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
