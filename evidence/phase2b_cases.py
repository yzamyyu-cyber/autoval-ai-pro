#!/usr/bin/env python3
"""Phase 2B — generalize the agent (MCD/JNJ/ORCL) and record extraction-only vs AI-assisted.

For each company this records: original extraction status, detected issues, the agent's
validated proposal, approval result, corrected extraction status, and valuation
availability. CAT/XOM are recorded as specialized (captive-finance / predecessor-successor)
without running a generic correction. Outputs a machine-readable evaluation matrix.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/phase2b_cases.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.reconciliation import detect_issues, investigate, save_record, apply_approved

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")
MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_evaluation_matrix.json")

# (ticker, kind, issue_override)
CASES = [
    ("MCD", "agent", None),
    ("JNJ", "agent", None),
    ("ORCL", "agent", None),
]

SPECIALIZED = [
    ("CAT", "specialized_captive_finance", "captive-finance arm; debt/interest tags not standalone"),
    ("XOM", "specialized_predecessor_successor", "predecessor-successor registrant identity"),
]


def run_agent_case(ticker, ua):
    row = {"ticker": ticker, "kind": "agent",
           "original_extraction": "failed", "issues": [], "proposal": None,
           "validation": None, "approval": None, "corrected_extraction": None,
           "valuation_available": None}
    try:
        ext = get_sec_financials(ticker, ua)
        row["original_extraction"] = "ok" if ext.get("debt_available") else "debt_blocked"
    except Exception as exc:
        row["original_extraction"] = f"failed: {type(exc).__name__}"
        return row
    issues = detect_issues(ext)
    row["issues"] = [i["category"] for i in issues]
    proposal = investigate(ext, ua, issue=issues[0] if issues else None)
    v = proposal.get("deterministic_validation", {})
    row["proposal"] = proposal.get("proposed_financial_value")
    row["validation"] = v.get("status")
    row["approval"] = proposal.get("approval_status")
    row["corrected_extraction"] = None
    row["valuation_available"] = ext.get("net_debt") is not None
    save_record(proposal, RECORDS_DIR)
    return row


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    matrix = []
    for ticker, kind, issue in CASES:
        try:
            matrix.append(run_agent_case(ticker, ua))
        except Exception as exc:
            matrix.append({"ticker": ticker, "kind": kind, "error": str(exc)})
    for ticker, kind, note in SPECIALIZED:
        matrix.append({"ticker": ticker, "kind": kind, "note": note,
                       "original_extraction": "specialized", "issues": [],
                       "validation": "deferred", "approval": "deferred"})

    with open(MATRIX, "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, default=str, ensure_ascii=False)

    print(json.dumps(matrix, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
