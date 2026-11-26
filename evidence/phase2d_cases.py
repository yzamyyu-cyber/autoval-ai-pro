#!/usr/bin/env python3
"""Phase 2D — custom-taxonomy recovery (ORCL, JNJ, MCD, PG).

Runs the agent for each company, records its source-backed proposal and validation, and
compares against independently established benchmarks (kept in THIS evaluation harness only,
never exposed to the agent). Writes a machine-readable evaluation matrix.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/phase2d_cases.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials, sec_lookup, fetch_json, FACTS_URL
from autoval.reconciliation import investigate, save_record

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")
MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_evaluation_matrix_2d.json")

# Independently established benchmarks (USD millions), for evaluation ONLY.
BENCHMARKS = {
    "ORCL": {"current_borrowings": 7_625, "noncurrent_borrowings": 117_712, "cash": 36_369,
             "marketable_securities": 708, "finance_leases": 9_185, "restricted_cash": 2_600},
    "JNJ": {"current_borrowings": 8_852, "long_term_debt": 35_799, "cash": 16_910,
            "current_marketable_securities": 318, "debt_less_cash_and_securities": 27_423},
    "MCD": {"long_term_debt": 39_820, "cash": 1_193, "debt_less_cash": 38_627},
    "PG": {"current_debt": 17_028, "long_term_debt": 21_897, "cash": 15_365,
           "debt_less_cash": 23_560},
}

ISSUES = {
    "ORCL": ("debt_unavailable", "Reconstruct complete debt (noncurrent + current borrowings, finance leases, cash)."),
    "JNJ": ("debt_unavailable", "Reconstruct current borrowings, long-term debt, cash and marketable securities."),
    "MCD": ("debt_unavailable", "Reconstruct long-term debt and cash; compute debt less cash."),
    "PG": ("debt_component_stale_nonzero", "Resolve current debt, long-term debt, cash and finance leases."),
}


def run(ticker, ua):
    row = {"ticker": ticker, "benchmark": BENCHMARKS[ticker]}
    try:
        ext = get_sec_financials(ticker, ua)
        row["original_extraction"] = "ok" if ext.get("debt_available") else "debt_blocked"
    except Exception as exc:
        row["original_extraction"] = f"failed: {type(exc).__name__}"
        cik, name = sec_lookup(ticker, ua)
        facts = fetch_json(FACTS_URL.format(cik=cik), ua)
        ext = {"ticker": ticker, "company": name, "shares": None, "net_debt": None,
               "total_debt": None, "debt_available": False, "cash_and_equivalents": None,
               "balance_sheet_asof": None, "source": {}}
    cat, summary = ISSUES[ticker]
    issue = {"issue_id": f"{ticker}.debt.recovery", "category": cat, "severity": "high",
             "summary": summary, "evidence": {}}
    p = investigate(ext, ua, issue=issue)
    v = p.get("deterministic_validation", {})
    row["proposed_value"] = p.get("proposed_financial_value")
    row["components"] = {t["tag"]: t.get("value") for t in (p.get("xbrl_tags") or [])}
    row["formula"] = p.get("derivation_formula")
    row["validation"] = v.get("status")
    row["approval"] = p.get("approval_status")
    row["filing_accession"] = (p.get("filing") or {}).get("accession")
    row["filing_url"] = (p.get("filing") or {}).get("url")
    row["uncertainty"] = p.get("remaining_uncertainty")
    save_record(p, RECORDS_DIR)
    return row


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    matrix = []
    for ticker in ("ORCL", "JNJ", "MCD", "PG"):
        try:
            matrix.append(run(ticker, ua))
        except Exception as exc:
            matrix.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    with open(MATRIX, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, default=str, ensure_ascii=False)
    print(json.dumps(matrix, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
