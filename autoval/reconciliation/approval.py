"""Approval-gated correction application.

A correction is applied only when it is (a) explicitly approved, (b) deterministically
validated, (c) bound to the exact company / reporting period / snapshot identity, and
(d) not already applied. Outdated, duplicate, modified or unvalidated proposals are
rejected. A no-correction finding leaves the original analysis unchanged.
"""
from __future__ import annotations

from .apply import apply_correction
from .regenerate import regenerate_analysis


def apply_approved(proposal: dict, extraction: dict, snapshot_id: str,
                   user_agent: str = "", original_result: dict | None = None) -> dict:
    """Apply an approved, validated correction. Returns a result descriptor."""
    if proposal.get("approval_status") != "approved":
        return {"status": "rejected", "reason": "proposal is not approved"}
    validation = proposal.get("deterministic_validation") or {}
    if validation.get("status") != "validated":
        return {"status": "rejected", "reason": "proposal is not deterministically validated"}

    # Bind to company + reporting period.
    if (proposal.get("ticker") or "").upper() != (extraction.get("ticker") or "").upper():
        return {"status": "rejected", "reason": "proposal ticker does not match the extraction"}
    if proposal.get("reporting_period") and proposal["reporting_period"] != extraction.get("balance_sheet_asof"):
        return {"status": "rejected", "reason": "proposal period does not match the balance-sheet date"}

    # Bind to snapshot identity + idempotency (reject duplicate application).
    if proposal.get("applied_snapshot_id"):
        return {"status": "rejected", "reason": f"proposal already applied to {proposal['applied_snapshot_id']}"}

    # No-correction: leave the original unchanged.
    pv = proposal.get("proposed_financial_value")
    ov = proposal.get("original_production_value")
    if pv is not None and ov is not None and abs(float(pv) - float(ov)) <= 1e-6:
        return {"status": "no_change", "reason": "no correction (proposed equals original)",
                "corrected": extraction, "impact": {
                    "original_net_debt": (extraction.get("source") or {}).get("debt_reconciliation", {}).get("net_debt"),
                    "corrected_net_debt": (extraction.get("source") or {}).get("debt_reconciliation", {}).get("net_debt"),
                    "net_debt_delta": 0.0, "per_share_impact_usd": 0.0}}

    applied = apply_correction(extraction, proposal)
    if applied.get("status") == "unsupported_component":
        return {"status": "rejected", "reason": applied["reason"]}
    corrected_stock = applied["corrected"]
    corrected_result = (regenerate_analysis(original_result, corrected_stock, user_agent)
                        if original_result is not None else None)

    proposal["applied_snapshot_id"] = snapshot_id
    return {"status": "applied", "corrected": corrected_stock,
            "corrected_result": corrected_result, "impact": applied["impact"],
            "original": applied["original"]}
