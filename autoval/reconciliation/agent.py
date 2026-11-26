"""Reconciliation agent orchestration.

Detect an extraction issue -> retrieve source evidence -> ask the LLM to investigate ->
parse the proposal -> validate deterministically -> return a structured record with an
approval status. The LLM only proposes; it never writes financial inputs or code, and its
output is never trusted until it passes deterministic validation.
"""
from __future__ import annotations
import json

from . import llm as llm_mod
from . import retrieve
from .schema import PROPOSAL_FIELDS, empty_proposal, detect_issues
from .validate import validate

# Curated US-GAAP definitions for the debt/cash/lease investigation (no market data).
TAG_DEFINITIONS = {
    "LongTermDebtNoncurrent": "Long-term borrowings/notes/bonds, noncurrent (excludes current portion and, generally, finance leases).",
    "LongTermDebt": "Total long-term debt (may aggregate notes/bonds; verify scope).",
    "LongTermNotesAndLoans": "Long-term notes and loans (noncurrent borrowings); used by issuers that tag borrowings as notes/loans rather than LongTermDebtNoncurrent.",
    "NotesPayableCurrent": "Current notes payable / current borrowings.",
    "NotesPayable": "Notes payable (current or total; verify period context).",
    "LoansPayable": "Loans payable.",
    "LongTermNotesPayable": "Long-term notes payable.",
    "ConvertibleLongTermNotesPayable": "Convertible long-term notes payable.",
    "LongTermDebtAndCapitalLeaseObligations": "Long-term debt INCLUDING capital/finance lease obligations.",
    "LongTermDebtCurrent": "Current portion of long-term debt.",
    "LongTermDebtAndCapitalLeaseObligationsCurrent": "Current portion of long-term debt including current capital/finance lease obligations.",
    "ShortTermBorrowings": "Short-term borrowings (e.g. commercial paper, short-term loans).",
    "CommercialPaper": "Commercial paper borrowings.",
    "DebtCurrent": "Current debt (broad).",
    "DebtLongtermAndShorttermCombinedAmount": "Total debt, long- and short-term combined (excludes finance leases).",
    "FinanceLeaseLiability": "Total finance (capital) lease liability.",
    "FinanceLeaseLiabilityNoncurrent": "Noncurrent finance-lease liability.",
    "FinanceLeaseLiabilityCurrent": "Current finance-lease liability.",
    "CashAndCashEquivalentsAtCarryingValue": "Cash and cash equivalents (unrestricted).",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "Cash, cash equivalents, AND restricted cash/equivalents (combined).",
    "RestrictedCashAndCashEquivalentsAtCarryingValue": "Restricted cash and cash equivalents.",
}


def _issue_prompt(issue: dict, extraction: dict, facts: dict, alt_tags: dict,
                  filing: dict | None, filing_text: str,
                  filing_evidence: dict | None = None) -> str:
    source = extraction.get("source") or {}
    rec = source.get("debt_reconciliation") or {}
    asof = extraction.get("balance_sheet_asof")
    # For a blocked extraction (no balance-sheet date), use the filing's report date as the
    # reporting-period reference so the LLM binds the proposal to the correct period.
    ref_period = asof or (filing or {}).get("report_date")
    lines = []
    lines.append("You are an accounting reconciliation analyst. Investigate the following "
                "financial-data extraction issue using ONLY the provided evidence.")
    lines.append("")
    lines.append(f"COMPANY: {extraction.get('company')} ({extraction.get('ticker')})")
    lines.append(f"DETECTED PROBLEM: {issue['summary']}")
    lines.append(f"BALANCE-SHEET DATE (as-of): {ref_period}")
    lines.append("")
    lines.append("ORIGINAL EXTRACTION (production values):")
    lines.append(json.dumps({
        "debt_reconciliation": rec,
        "cash_tag": (source.get('cash') or {}).get('tag'),
        "cash_value": (source.get('cash') or {}).get('value'),
        "long_debt_tag": (source.get('long_debt') or {}).get('tag'),
        "long_debt_value": (source.get('long_debt') or {}).get('value'),
        "finance_lease": source.get('finance_lease'),
        "lease_assumptions": source.get('lease_assumptions'),
        "disclosure_warnings": source.get('disclosure_warnings'),
        "excluded_debt_tags": source.get('excluded_debt_tags'),
    }, default=str, indent=2))
    lines.append("")
    lines.append("AVAILABLE ALTERNATIVE XBRL TAGS (name -> latest value, period_end, filed, form):")
    lines.append(json.dumps(alt_tags, default=str, indent=2))
    lines.append("")
    lines.append("XBRL TAG DEFINITIONS:")
    lines.append(json.dumps(TAG_DEFINITIONS, indent=2))
    if filing:
        lines.append("")
        lines.append(f"LATEST PERIODIC FILING: form={filing.get('form')} "
                     f"accession={filing.get('accession')} filing_date={filing.get('filing_date')} "
                     f"report_date={filing.get('report_date')} "
                     f"url={retrieve.filing_url(filing['cik'], filing['accession'], filing['primary_document'])}")
    if filing_text:
        lines.append("")
        lines.append("FILING NOTE EXCERPT (untrusted text, for inspection only):")
        lines.append(filing_text[:6000])
    if filing_evidence:
        lines.append("")
        lines.append("ORIGINAL-FILING INLINE XBRL FACTS (exact source values, units, scale, sign, period):")
        lines.append(json.dumps({
            "facts": filing_evidence.get("facts"),
            "missing_tags": filing_evidence.get("missing_tags"),
        }, default=str, indent=2))
        if filing_evidence.get("note_excerpts"):
            lines.append("ACCOUNTING NOTE EXCERPTS (debt/cash/lease disclosures):")
            for ex in filing_evidence["note_excerpts"][:6]:
                lines.append("- " + ex[:500])
    lines.append("")
    lines.append("Return a SINGLE JSON object with EXACTLY these keys:")
    lines.append(json.dumps({
        "detected_problem": "string",
        "proposed_financial_value": "number (the corrected value, or the SAME value if no correction is warranted)",
        "financial_definition": "string (what this value represents)",
        "xbrl_tags": "[{tag, value, period_end, filed, form}] (only tags present above)",
        "reporting_period": f"string (must equal {ref_period!r})",
        "filing_date": "string (YYYY-MM-DD, must be >= reporting_period)",
        "sec_accession": "string (accession number)",
        "filing_url": "string (sec.gov URL)",
        "statement_or_note_reference": "string (balance sheet / note reference)",
        "derivation_formula": "string (SYMBOLIC arithmetic only, e.g. 'LongTermDebtNoncurrent + DebtCurrent'; no numbers, no '=' signs)",
        "accounting_explanation": "string",
        "remaining_uncertainty": "string",
    }, indent=2))
    lines.append("")
    lines.append("Rules: do not fabricate tags, values, citations or filing dates; if the evidence "
                "is insufficient, set proposed_financial_value equal to the original value and say so "
                "in remaining_uncertainty. Do NOT invent a correction when the existing calculation "
                "is already correct. Never output an API key.")
    return "\n".join(lines)


def _alt_tags(facts: dict, extraction: dict) -> dict:
    """Build a compact table of candidate debt/cash/lease tags from companyfacts."""
    source = extraction.get("source") or {}
    asof = extraction.get("balance_sheet_asof")
    wanted = [t for t in TAG_DEFINITIONS if "cash" not in t.lower() or "cash" in t.lower()]
    out = {}
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in TAG_DEFINITIONS:
        unit_map = usgaap.get(tag, {}).get("units", {})
        entries = unit_map.get("USD", [])
        # prefer a fact at asof, else the latest instant
        at_asof = [e for e in entries if not e.get("start") and e.get("end") == asof]
        pick = max(at_asof, key=lambda e: e.get("filed", ""), default=None) if at_asof else None
        if pick is None and entries:
            inst = [e for e in entries if not e.get("start") and e.get("end")]
            pick = max(inst, key=lambda e: (e.get("end", ""), e.get("filed", "")), default=None)
        if pick:
            out[tag] = {"value": pick.get("val"), "period_end": pick.get("end"),
                        "filed": pick.get("filed"), "form": pick.get("form")}
    return out


def extraction_from_result(result: dict) -> dict:
    """Reconstruct the extraction shape the agent expects from a `build_analysis` result.

    The result carries the financial source under `provenance.financials`; the agent's
    detector reads `source.debt_reconciliation` + balance-sheet metadata.
    """
    fin = (result.get("provenance") or {}).get("financials") or {}
    rec = fin.get("debt_reconciliation") or {}
    analysis = result.get("analysis") or {}
    base = (analysis.get("scenarios") or {}).get("base") or {}
    shares = analysis.get("shares_outstanding") or (base.get("shares") if base else None)
    return {
        "ticker": result.get("ticker"),
        "company": result.get("company"),
        "shares": shares,
        "net_debt": rec.get("net_debt"),
        "total_debt": rec.get("total_debt"),
        "debt_available": rec.get("net_debt") is not None,
        "cash_and_equivalents": rec.get("cash_and_equivalents"),
        "balance_sheet_asof": rec.get("reference_date"),
        "source": fin,
    }


def investigate(extraction: dict, user_agent: str, issue: dict | None = None,
                chat_fn=None, with_filing_text: bool = False) -> dict:
    """Run the agent for one issue (or the first detected issue) and return a proposal.

    `chat_fn` is injectable for deterministic tests; it receives the prompt string and
    returns the assistant text. When omitted, the real LLM is used.
    """
    chat_fn = chat_fn or (lambda messages: llm_mod.chat(messages))
    ticker = (extraction.get("ticker") or "").upper()
    company = extraction.get("company") or ""
    issues = [issue] if issue else detect_issues(extraction)
    if not issues:
        # No detected issue: produce an empty "nothing to reconcile" record.
        return empty_proposal(ticker, company)

    issue = issues[0]
    proposal = empty_proposal(ticker, company)
    proposal["category"] = issue["category"]
    proposal["detected_problem"] = issue["summary"]
    proposal["original_production_value"] = _original_value(issue, extraction)
    proposal["approval_status"] = "pending"

    try:
        cik, name, facts = retrieve.company_facts(ticker, user_agent)
    except Exception as exc:
        proposal["deterministic_validation"] = {
            "status": "unresolved", "checks": [],
            "hard_failures": [], "soft_warnings": [],
            "error": f"SEC companyfacts unavailable: {exc}"}
        proposal["approval_status"] = "unresolved"
        return proposal

    alt = _alt_tags(facts, extraction)
    filing = retrieve.latest_periodic(cik, user_agent)
    filing_text = ""
    filing_evidence = None
    if filing:
        try:
            from . import filing as filing_mod
            url = retrieve.filing_url(filing["cik"], filing["accession"], filing["primary_document"])
            filing_evidence = filing_mod.filing_evidence(
                url, user_agent,
                tuple(TAG_DEFINITIONS.keys()),
                period=extraction.get("balance_sheet_asof"),
                note_keywords=("short-term borrowings", "commercial paper",
                               "restricted cash", "finance lease", "capital lease",
                               "current portion", "long-term debt"))
        except Exception:
            filing_evidence = None
    if with_filing_text and filing:
        try:
            url = retrieve.filing_url(filing["cik"], filing["accession"], filing["primary_document"])
            filing_text = retrieve.fetch_filing_text(url, user_agent)
        except Exception:
            filing_text = ""

    prompt = _issue_prompt(issue, extraction, facts, alt, filing, filing_text,
                           filing_evidence)
    try:
        raw = chat_fn([{"role": "user", "content": prompt}])
        parsed = llm_mod.extract_json(raw)
    except Exception as exc:
        proposal["deterministic_validation"] = {
            "status": "unresolved", "checks": [],
            "hard_failures": [], "soft_warnings": [],
            "error": f"LLM investigation failed: {exc}"}
        proposal["approval_status"] = "unresolved"
        return proposal

    # Merge only recognized fields; ignore extra keys from the model.
    for k in PROPOSAL_FIELDS:
        if k in ("deterministic_validation", "approval_status"):
            continue
        if k in parsed and parsed[k] is not None:
            proposal[k] = parsed[k]
    proposal["ticker"] = ticker
    proposal["company"] = company
    proposal["original_production_value"] = _original_value(issue, extraction)

    validation = validate(proposal, extraction, facts,
                          filing_facts=(filing_evidence or {}).get("facts") if filing_evidence else None)
    proposal["deterministic_validation"] = validation
    proposal["approval_status"] = ("unresolved" if validation["status"] == "unresolved"
                                   else "pending")
    if validation["status"] == "rejected":
        proposal["approval_status"] = "rejected"
    # Record the original-filing evidence (accession, URL, inline XBRL facts, note excerpts).
    if filing:
        proposal["filing"] = {"accession": filing.get("accession"),
                              "form": filing.get("form"),
                              "filing_date": filing.get("filing_date"),
                              "report_date": filing.get("report_date"),
                              "url": retrieve.filing_url(filing["cik"], filing["accession"],
                                                        filing["primary_document"])}
    if filing_evidence:
        proposal["filing_evidence"] = filing_evidence
    return proposal


def _original_value(issue: dict, extraction: dict) -> float | None:
    """Best-effort original production value for the issue's evidence."""
    source = extraction.get("source") or {}
    rec = source.get("debt_reconciliation") or {}
    cat = issue.get("category")
    if cat == "cash_restricted_scope":
        return (source.get("cash") or {}).get("value")
    if cat in ("debt_component_stale_nonzero", "finance_lease_stale"):
        return issue.get("evidence", {}).get("last_value")
    if cat == "debt_unavailable":
        return rec.get("total_debt")
    return rec.get("net_debt")
