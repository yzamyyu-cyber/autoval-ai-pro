"""AI financial-data reconciliation agent (reusable within AutoVal).

Public API:
  detect_issues(extraction) -> list[dict]
  investigate(extraction, user_agent, issue=None, chat_fn=None) -> proposal dict
  validate(proposal, extraction, facts) -> dict
  apply_correction(extraction, proposal) -> {original, corrected, impact}
  save_record(proposal, out_dir) -> path
"""
from .schema import detect_issues, empty_proposal, PROPOSAL_FIELDS
from .agent import investigate, extraction_from_result
from .validate import validate
from .apply import apply_correction
from .regenerate import regenerate_analysis, recompute_wacc
from .approval import apply_approved
from .store import save_record, load_record, list_records
from . import filing

__all__ = [
    "detect_issues", "empty_proposal", "PROPOSAL_FIELDS",
    "investigate", "extraction_from_result", "validate", "apply_correction",
    "regenerate_analysis", "recompute_wacc", "apply_approved",
    "save_record", "load_record", "list_records", "filing",
]
