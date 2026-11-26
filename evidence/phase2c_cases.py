#!/usr/bin/env python3
"""Phase 2C — original-filing intelligence for financial recovery.

Runs the agent (now with original-filing inline-XBRL + note retrieval) for PG, ORCL, MCD
and JNJ, records machine-readable proposals, and writes a machine-readable evaluation
matrix. Expected benchmark values are NOT passed to the agent.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/phase2c_cases.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import get_sec_financials
from autoval.reconciliation import detect_issues, investigate, save_record

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")
MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_evaluation_matrix_2c.json")

MANUAL = {
    "ORCL": {"issue_id": "ORCL.long_debt.missing",
             "category": "debt_unavailable",
             "severity": "high",
             "summary": ("Noncurrent long-term debt was not reported at the cash reporting date. "
                         "Inspect the original balance sheet and debt notes to reconstruct complete "
                         "debt without double-counting."),
             "evidence": {}},
    "PG": {"issue_id": "PG.current_debt.restricted_cash",
           "category": "debt_component_stale_nonzero",
           "severity": "high",
           "summary": ("Resolve current debt, unrestricted vs restricted cash, and finance leases "
                       "from the original statements."),
           "evidence": {}},
}


def run(ticker, ua):
    row = {"ticker": ticker, "original_extraction": None, "issues": [],
           "proposal": None, "validation": None, "approval": None,
           "filing_accession": None, "filing_url": None, "inline_facts": None}
    try:
        ext = get_sec_financials(ticker, ua)
        row["original_extraction"] = "ok" if ext.get("debt_available") else "debt_blocked"
    except Exception as exc:
        row["original_extraction"] = f"failed: {type(exc).__name__}"
        ext = None
    if ext is None:
        # still investigate via companyfacts + filing (recovery from blocked extraction)
        from autoval.sec import sec_lookup, fetch_json, FACTS_URL
        cik, name = sec_lookup(ticker, ua)
        facts = fetch_json(FACTS_URL.format(cik=cik), ua)
        from autoval.reconciliation import agent as agent_mod
        # build a minimal extraction from raw facts for the detector to inspect
        ext = {"ticker": ticker, "company": name, "shares": None, "net_debt": None,
               "total_debt": None, "debt_available": False, "cash_and_equivalents": None,
               "balance_sheet_asof": None, "source": {}}
    issues = detect_issues(ext) if ext else []
    row["issues"] = [i["category"] for i in issues]
    issue = MANUAL.get(ticker) or (issues[0] if issues else None)
    proposal = investigate(ext, ua, issue=issue)
    v = proposal.get("deterministic_validation", {})
    row["proposal"] = proposal.get("proposed_financial_value")
    row["validation"] = v.get("status")
    row["approval"] = proposal.get("approval_status")
    fil = proposal.get("filing") or {}
    row["filing_accession"] = fil.get("accession")
    row["filing_url"] = fil.get("url")
    ev = proposal.get("filing_evidence") or {}
    row["inline_facts"] = {t: (f.get("value") if f else None) for t, f in (ev.get("facts") or {}).items()}
    row["missing_tags"] = ev.get("missing_tags")
    row["note_excerpts"] = (ev.get("note_excerpts") or [])[:3]
    save_record(proposal, RECORDS_DIR)
    return row


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    matrix = []
    for ticker in ("PG", "ORCL", "MCD", "JNJ"):
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
