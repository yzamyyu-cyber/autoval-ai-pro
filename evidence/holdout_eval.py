#!/usr/bin/env python3
"""Phase 2F — frozen unseen-company evaluation.

Runs Method A (deterministic extraction), then the AI agent (Method B raw LLM proposal ->
Method C validated) for five holdout companies. Records results to holdout_results.csv and
sanitized JSON records. Maximum five paid LLM calls (one per company).

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/holdout_eval.py
"""
from __future__ import annotations
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.reconciliation import detect_issues, investigate, save_record

HOLDOUT = ("PFE", "INTC", "DE", "PEP", "CSCO")
RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdout_results.csv")


def method_a(ticker, ua):
    try:
        ext = get_sec_financials(ticker, ua)
        return {"status": "ok" if ext.get("debt_available") else "debt_blocked",
                "net_debt": ext.get("net_debt"), "total_debt": ext.get("total_debt"),
                "shares": ext.get("shares"), "diluted_shares": ext.get("diluted_shares"),
                "extraction": ext}
    except Exception as exc:
        return {"status": f"failed: {type(exc).__name__}", "extraction": None}


def run(ticker, ua):
    row = {"ticker": ticker, "method_a": None, "issues": [],
           "llm_proposed_value": None, "llm_formula": None,
           "validation": None, "approval": None, "elapsed_s": None}
    a = method_a(ticker, ua)
    row["method_a"] = a["status"]
    ext = a.get("extraction")
    if ext is None:
        return row
    issues = detect_issues(ext)
    row["issues"] = [i["category"] for i in issues]
    start = time.time()
    try:
        proposal = investigate(ext, ua, issue=issues[0] if issues else None)
        v = proposal.get("deterministic_validation", {})
        row["llm_proposed_value"] = proposal.get("proposed_financial_value")
        row["llm_formula"] = proposal.get("derivation_formula")
        row["validation"] = v.get("status")
        row["approval"] = proposal.get("approval_status")
        save_record(proposal, RECORDS_DIR)
    except Exception as exc:
        row["validation"] = f"error: {type(exc).__name__}"
    row["elapsed_s"] = round(time.time() - start, 1)
    return row


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    rows = []
    for t in HOLDOUT:
        try:
            rows.append(run(t, ua))
        except Exception as exc:
            rows.append({"ticker": t, "method_a": f"error: {type(exc).__name__}"})
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
