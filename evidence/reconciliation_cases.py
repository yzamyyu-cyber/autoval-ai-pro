#!/usr/bin/env python3
"""AI financial-data reconciliation — actual case studies (real SEC + real LLM).

Runs the reconciliation agent for three issuers, records machine-readable proposals, and
prints a summary. The expected benchmark values are NOT passed to the agent; they are
recorded separately for evaluation in AI_RECONCILIATION_EVALUATION.md.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/reconciliation_cases.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.reconciliation import detect_issues, investigate, apply_correction, save_record

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")

MANUAL_ISSUES = {
    "WMT": {
        "issue_id": "WMT.net_debt.historical_discrepancy",
        "category": "net_debt_historical_discrepancy",
        "severity": "high",
        "summary": ("Historical net debt was reported as $45.7B in a prior analysis, but the "
                    "current extraction computes ~$35.2B. Investigate the finance-lease and "
                    "cash treatment to identify the cause of the discrepancy and the negative "
                    "five-year DCF."),
        "evidence": {},
    },
    "UPS": {
        "issue_id": "UPS.debt_finance_lease.control",
        "category": "debt_finance_lease_control",
        "severity": "low",
        "summary": ("Control case: verify the existing debt + finance-lease reconciliation is "
                    "correct (short-term borrowings zero per the commercial-paper note; finance "
                    "lease already included in LongTermDebtAndCapitalLeaseObligations). Do not "
                    "invent a correction if the current calculation is already correct."),
        "evidence": {},
    },
}


def run_case(ticker: str, ua: str) -> dict:
    ext = get_sec_financials(ticker, ua)
    issues = detect_issues(ext)
    if ticker in MANUAL_ISSUES:
        issue = MANUAL_ISSUES[ticker]
    elif issues:
        issue = issues[0]
    else:
        issue = None
    proposal = investigate(ext, ua, issue=issue)
    proposal["detected_issues"] = [i["category"] for i in issues]
    # before/after impact when a numeric correction is proposed and validated
    impact = None
    if (proposal.get("deterministic_validation", {}).get("status") == "validated"
            and proposal.get("proposed_financial_value") is not None):
        try:
            impact = apply_correction(ext, proposal)["impact"]
        except Exception:
            impact = None
    proposal["before_after_impact"] = impact
    record_path = save_record(proposal, RECORDS_DIR)
    return {"extraction": ext, "proposal": proposal, "record": record_path}


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT to 'AppName contact@example.com'")
        return 1
    results = {}
    for ticker in ("PG", "WMT", "UPS"):
        try:
            results[ticker] = run_case(ticker, ua)
        except Exception as exc:
            print(f"{ticker}: ERROR {exc}")
            results[ticker] = {"error": str(exc)}

    print("\n=== Reconciliation case-study summary ===\n")
    for ticker, r in results.items():
        if "error" in r:
            print(f"{ticker}: ERROR {r['error']}")
            continue
        p = r["proposal"]
        v = p.get("deterministic_validation", {})
        print(f"{ticker}: status={v.get('status')} approval={p.get('approval_status')}")
        print(f"  detected_issues={p.get('detected_issues')}")
        print(f"  original_value={p.get('original_production_value')} "
              f"proposed_value={p.get('proposed_financial_value')}")
        print(f"  definition={p.get('financial_definition')}")
        print(f"  formula={p.get('derivation_formula')}")
        print(f"  note_ref={p.get('statement_or_note_reference')}")
        print(f"  uncertainty={p.get('remaining_uncertainty')}")
        if p.get("before_after_impact"):
            imp = p["before_after_impact"]
            print(f"  impact: field={imp.get('field')} net_debt_delta={imp.get('net_debt_delta')} "
                  f"per_share={imp.get('per_share_impact_usd')}")
        print()
    print(f"records written to {RECORDS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
