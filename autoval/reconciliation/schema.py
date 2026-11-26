"""Structured reconciliation proposal schema and issue detection (reusable).

The agent never writes financial inputs directly. It produces a *proposal* conforming to
`PROPOSAL_FIELDS`, which the deterministic validator (validate.py) checks against the raw
SEC facts before any approval. The proposal records the original production value and the
proposed value side by side so the original analysis is always preserved.
"""
from __future__ import annotations

# Canonical proposal fields (Task 2). Every reconciliation record carries these.
PROPOSAL_FIELDS = (
    "company", "ticker",
    "detected_problem",
    "original_production_value",
    "proposed_financial_value",
    "financial_definition",
    "xbrl_tags",
    "reporting_period",
    "filing_date",
    "sec_accession",
    "filing_url",
    "statement_or_note_reference",
    "derivation_formula",
    "accounting_explanation",
    "deterministic_validation",
    "remaining_uncertainty",
    "approval_status",
)

APPROVAL_STATES = ("pending", "approved", "rejected", "unresolved")

# Issue categories surfaced by the detector.
ISSUE_CATEGORIES = (
    "debt_component_stale_nonzero",
    "debt_unavailable",
    "cash_restricted_scope",
    "finance_lease_double_count_risk",
    "finance_lease_stale",
)


def detect_issues(extraction: dict) -> list[dict]:
    """Detect reconciliation issues from a `get_sec_financials` output.

    Returns a list of issue descriptors with the evidence that triggered each one.
    """
    ticker = (extraction.get("ticker") or "").upper()
    source = extraction.get("source") or {}
    asof = source.get("debt_reconciliation", {}).get("reference_date") or extraction.get("balance_sheet_asof")
    issues: list[dict] = []

    # 1. Stale nonzero debt components (debt reconciliation blocked or partially assumed).
    for e in source.get("excluded_debt_tags") or []:
        if e.get("status") == "stale_nonzero":
            issues.append({
                "issue_id": f"{ticker}.{e.get('tag')}.stale_nonzero",
                "category": "debt_component_stale_nonzero",
                "severity": "high",
                "summary": (f"Debt component '{e.get('tag')}' is only reported at a stale date "
                            f"{e.get('last_end')} with nonzero value {e.get('last_value')}; "
                            f"the current-period ({asof}) value is unresolved."),
                "evidence": {"tag": e.get("tag"), "status": e.get("status"),
                             "last_end": e.get("last_end"), "last_value": e.get("last_value"),
                             "asof": asof},
            })

    # 2. Debt entirely unavailable (blocked), only when a debt reconciliation was
    #    actually attempted (avoids a spurious flag for synthetic/demo results).
    rec = source.get("debt_reconciliation") or {}
    has_debt_context = bool(rec or source.get("excluded_debt_tags") or source.get("long_debt"))
    if has_debt_context and not extraction.get("debt_available"):
        issues.append({
            "issue_id": f"{ticker}.debt.unavailable",
            "category": "debt_unavailable",
            "severity": "high",
            "summary": "Total debt / net debt could not be reconciled (debt reconciliation blocked).",
            "evidence": {"asof": asof,
                         "warnings": source.get("disclosure_warnings") or []},
        })

    # 3. Cash tag migration to a restricted-cash-inclusive tag (unrestricted vs restricted).
    cash_fact = source.get("cash") or {}
    if cash_fact.get("tag") == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents":
        issues.append({
            "issue_id": f"{ticker}.cash.restricted_scope",
            "category": "cash_restricted_scope",
            "severity": "medium",
            "summary": (f"Cash uses the combined '{cash_fact.get('tag')}' tag, which includes "
                        f"restricted cash and restricted-cash equivalents; net debt may therefore "
                        f"treat restricted cash as freely available."),
            "evidence": {"tag": cash_fact.get("tag"), "value": cash_fact.get("value"),
                         "end": cash_fact.get("end")},
        })

    # 4. Finance-lease stale (material lease definition unresolved).
    for e in source.get("lease_excluded") or []:
        if e.get("status") == "stale":
            issues.append({
                "issue_id": f"{ticker}.finance_lease.stale",
                "category": "finance_lease_stale",
                "severity": "medium",
                "summary": (f"Finance-lease liability last reported {e.get('last_end')} = "
                            f"{e.get('last_value')} (not at {asof}); treated as zero — "
                            f"material lease definition unresolved."),
                "evidence": {"tag": e.get("tag"), "last_end": e.get("last_end"),
                             "last_value": e.get("last_value"), "asof": asof},
            })

    # 5. Finance-lease double-count risk marker (informational, for the agent to confirm).
    long_debt = source.get("long_debt") or {}
    if long_debt.get("tag") in ("LongTermDebtAndCapitalLeaseObligations",):
        fl = source.get("finance_lease") or {}
        if fl.get("value"):
            issues.append({
                "issue_id": f"{ticker}.finance_lease.double_count_risk",
                "category": "finance_lease_double_count_risk",
                "severity": "low",
                "summary": (f"Long-term debt tag '{long_debt.get('tag')}' is lease-inclusive; "
                            f"verify finance-lease liability ({fl.get('value')}) is not double-counted."),
                "evidence": {"long_debt_tag": long_debt.get("tag"),
                             "finance_lease_value": fl.get("value"), "asof": asof},
            })

    return issues


def empty_proposal(ticker: str = "", company: str = "") -> dict:
    return {k: None for k in PROPOSAL_FIELDS} | {
        "ticker": ticker.upper(), "company": company,
        "deterministic_validation": {"status": "unresolved", "checks": []},
        "approval_status": "pending",
        "xbrl_tags": [],
    }
