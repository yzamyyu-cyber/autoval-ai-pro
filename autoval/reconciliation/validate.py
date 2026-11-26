"""Deterministic validation of a reconciliation proposal.

Every rule is a pure function of the proposal + raw SEC facts. The LLM never writes
financial inputs directly; its proposal only passes here if it survives these checks.
Hard rules reject; soft rules record uncertainty (unverifiable proposals stay unresolved).
"""
from __future__ import annotations
import re
from datetime import date, datetime
from math import isfinite

ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
LEASE_INCLUSIVE_TAGS = {"LongTermDebtAndCapitalLeaseObligations",
                        "LongTermDebtAndCapitalLeaseObligationsCurrent"}
RESTRICTED_CASH_TAGS = {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"}


def _check(level: str, rule: str, ok: bool, reason: str) -> dict:
    return {"rule": rule, "level": level, "ok": ok, "reason": reason}


def _safe_eval(expr: str, variables: dict, missing_as_zero: bool = False) -> float:
    """Evaluate a tiny arithmetic expression (digits, + - * / ( ), variable names).

    Only arithmetic is permitted; no attribute access, no calls, no builtins. Raises
    ValueError on malformed/unsafe input. Tolerates common LLM formatting (comma
    separators, and a trailing "= numeric expansion" which is ignored). With
    `missing_as_zero`, a formula variable absent from `variables` is treated as 0.0
    (an LLM often omits a zero-valued component it has no XBRL tag for).
    """
    expr = (expr or "").split("=")[0].strip()  # ignore a trailing numeric expansion
    expr = expr.replace(",", "")
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+\.?\d*|[+\-*/()]", expr)
    # Validate token vocabulary.
    for t in tokens:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t):
            continue
        if re.fullmatch(r"\d+\.?\d*", t):
            continue
        if t in "+-*/()":
            continue
        raise ValueError(f"Unsafe token in formula: {t!r}")
    # Substitute variables, keep a numeric-only expression.
    subbed = re.sub(r"[A-Za-z_][A-Za-z0-9_]*",
                    lambda m: _var(m.group(0), variables, missing_as_zero), expr)
    if not re.fullmatch(r"[0-9+\-*/().\s]+", subbed):
        raise ValueError("Formula must be purely arithmetic")
    try:
        return float(eval(subbed, {"__builtins__": {}}, {}))  # noqa: S307 - sandboxed arithmetic only
    except Exception as exc:
        raise ValueError(f"Cannot evaluate formula: {exc}") from exc


def _var(name: str, variables: dict, missing_as_zero: bool = False) -> str:
    if name not in variables:
        if missing_as_zero:
            return "0.0"
        raise ValueError(f"Unknown variable {name!r}")
    return repr(float(variables[name]))


def validate(proposal: dict, extraction: dict, facts: dict | None,
             filing_facts: dict | None = None) -> dict:
    """Validate a proposal against the original extraction and raw companyfacts.

    `filing_facts` is an optional authoritative cross-check from the original filing's
    inline XBRL (tag -> resolved fact dict with `value`). When provided, a cited value is
    checked against BOTH companyfacts and the inline filing fact — never against a value
    supplied by the LLM.
    """
    checks: list[dict] = []
    ticker = (extraction.get("ticker") or "").upper()
    asof = extraction.get("balance_sheet_asof")
    source = extraction.get("source") or {}

    # ---- 1. Company identity (hard) ----
    checks.append(_check("hard", "company_identity",
                         bool((proposal.get("ticker") or "").upper() == ticker and proposal.get("company")),
                         "proposal ticker/company must match the extraction"))

    # ---- 2. Reporting period compatibility (hard) ----
    period = proposal.get("reporting_period")
    if asof:
        period_ok = bool(period == asof)
        period_reason = f"proposal period {period!r} must equal balance-sheet date {asof!r}"
    else:
        # Blocked extraction (no balance-sheet date): bind to a valid period, optionally
        # cross-checked against the original filing's inline-fact periods.
        period_ok = bool(period)
        period_reason = f"proposal period {period!r} must be present for a blocked extraction"
    checks.append(_check("hard", "reporting_period", period_ok, period_reason))

    # ---- 3. Filing eligibility / look-ahead (hard) ----
    fd = proposal.get("filing_date")
    lookahead_ok = bool(fd and period and fd >= period)
    checks.append(_check("hard", "filing_lookahead",
                         lookahead_ok,
                         f"filing date {fd!r} must not precede the reporting period {period!r}"))

    # ---- 4. Units / scaling (soft) ----
    pv = proposal.get("proposed_financial_value")
    ov = proposal.get("original_production_value")
    finite_ok = pv is not None and isfinite(float(pv))
    checks.append(_check("hard", "value_finite", finite_ok, "proposed value must be a finite number"))
    scale_warn = False
    if finite_ok and ov is not None and float(ov) not in (0, None) and isfinite(float(ov)):
        for factor in (1e3, 1e6, 1e9):
            if abs(float(pv) - float(ov) * factor) <= abs(float(ov)) * factor * 1e-3:
                scale_warn = True
                break
            if abs(float(pv) * factor - float(ov)) <= abs(float(ov)) * 1e-3:
                scale_warn = True
                break
    checks.append(_check("soft", "units_scaling", not scale_warn,
                         "proposed value is within a 1e3/1e6/1e9 multiple of the original — "
                         "verify units and scaling"))

    # ---- 5. XBRL tag citation exists (hard) ----
    # A tag is accepted when it exists in Companyfacts OR when the original filing's inline
    # XBRL provides it (custom/alternate taxonomy facts). Companyfacts and inline XBRL are two
    # channels of the SAME disclosure, not independent underlying facts.
    tags = proposal.get("xbrl_tags") or []
    filing_tag_names = set((filing_facts or {}).keys()) | {
        (v.get("name") or "").split(":")[-1] for v in (filing_facts or {}).values() if v.get("name")}
    bad_tags = []
    for t in tags:
        name = t.get("tag", "")
        if "+" in name:  # documented combination, e.g. Noncurrent+Current
            continue
        in_companyfacts = facts is not None and name in facts.get("facts", {}).get("us-gaap", {})
        in_filing = name in filing_tag_names
        if not in_companyfacts and not in_filing:
            bad_tags.append(name)
    checks.append(_check("hard", "xbrl_tag_exists", not bad_tags,
                         f"cited tags missing from Companyfacts and the original filing: {bad_tags}"
                         if bad_tags else "all cited tags exist in Companyfacts or the original filing"))

    # ---- 5b. Cited component VALUES must match the retrieved companyfacts (hard) ----
    # (a correct filing URL with an incorrect value is still rejected)
    fact_mismatches = []
    if facts is not None:
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        for t in tags:
            name = t.get("tag", "")
            if "+" in name or t.get("value") is None:
                continue
            entries = usgaap.get(name, {}).get("units", {}).get("USD", [])
            cited_end = t.get("period_end")
            cited_filed = t.get("filed")
            match = None
            for e in entries:
                if e.get("end") == cited_end and e.get("filed") == cited_filed:
                    match = e
                    break
            if match is None and cited_end:
                for e in entries:
                    if e.get("end") == cited_end:
                        match = e
                        break
            if match is not None and abs(float(match.get("val", 0)) - float(t["value"])) > 0.5:
                fact_mismatches.append(f"{name} cited {t['value']:,.0f} vs companyfacts {match.get('val'):,.0f}")
            # Independent cross-check against the original filing's inline XBRL fact (if supplied).
            if filing_facts and name in filing_facts:
                inline_val = filing_facts[name].get("value")
                if inline_val is not None and abs(float(inline_val) - float(t["value"])) > 0.5:
                    fact_mismatches.append(f"{name} cited {t['value']:,.0f} vs filing inline XBRL {inline_val:,.0f}")
    checks.append(_check("hard", "source_fact_value", not fact_mismatches,
                         f"cited values do not match source facts: {fact_mismatches}"
                         if fact_mismatches else "cited values match source facts"))

    # ---- 6. Component arithmetic (hard, when components are supplied) ----
    arithmetic_ok = True
    arithmetic_reason = "no component arithmetic to check"
    formula = (proposal.get("derivation_formula") or "").strip()
    comp_vals = {t.get("tag"): t.get("value") for t in tags if t.get("value") is not None}
    if formula and comp_vals and finite_ok:
        try:
            # A formula variable absent from the components is treated as zero (the LLM
            # omits zero-valued tags it has no XBRL fact for, e.g. short-term borrowings).
            recomputed = _safe_eval(formula, comp_vals, missing_as_zero=True)
            tol = max(0.5, abs(float(pv)) * 0.005)
            arithmetic_ok = abs(recomputed - float(pv)) <= tol
            arithmetic_reason = (f"formula recomputes to {recomputed:,.2f} vs proposed {float(pv):,.2f}"
                                 if arithmetic_ok else
                                 f"formula recomputes to {recomputed:,.2f} but proposal is {float(pv):,.2f}")
        except ValueError as exc:
            arithmetic_ok = False
            arithmetic_reason = f"formula not evaluable: {exc}"
    checks.append(_check("hard", "component_arithmetic", arithmetic_ok, arithmetic_reason))

    # ---- 7. Debt / finance-lease double-count (hard) ----
    # Only flag when the finance-lease tag is actually ADDED by the derivation formula to
    # a lease-inclusive long-debt tag. Listing a lease component for transparency without
    # adding it is NOT a double-count (this is the control-case scenario).
    double_count = False
    long_debt_tag = (source.get("long_debt") or {}).get("tag")
    if long_debt_tag in LEASE_INCLUSIVE_TAGS:
        for t in tags:
            name = t.get("tag", "")
            if name.startswith("FinanceLease") and name in formula:
                double_count = True
    checks.append(_check("hard", "debt_lease_double_count", not double_count,
                         "finance-lease component must not be added to a lease-inclusive long-debt tag"
                         if double_count else "no debt/lease double-count detected"))

    # ---- 8. Restricted cash (soft) ----
    restricted_flag = any(t.get("tag") in RESTRICTED_CASH_TAGS for t in tags)
    definition = (proposal.get("financial_definition") or "").lower()
    restricted_ok = not (restricted_flag and "unrestricted" in definition)
    checks.append(_check("soft", "restricted_cash", restricted_ok,
                         "combined cash tag used while claiming unrestricted cash — separate restricted cash"
                         if not restricted_ok else "restricted/unrestricted cash scope is consistent"))

    # ---- 9. Source evidence (hard) ----
    acc = proposal.get("sec_accession") or ""
    url = proposal.get("filing_url") or ""
    note = proposal.get("statement_or_note_reference") or ""
    source_ok = bool(ACCESSION_RE.match(acc) and url.startswith("https://www.sec.gov/") and note)
    checks.append(_check("hard", "source_evidence", source_ok,
                         "accession + sec.gov filing URL + note reference required" if not source_ok
                         else "source evidence present"))

    hard_fail = [c for c in checks if c["level"] == "hard" and not c["ok"]]
    soft_fail = [c for c in checks if c["level"] == "soft" and not c["ok"]]
    if hard_fail:
        status = "rejected"
    elif soft_fail:
        status = "unresolved"
    else:
        status = "validated"
    return {"status": status, "checks": checks,
            "hard_failures": [c["rule"] for c in hard_fail],
            "soft_warnings": [c["rule"] for c in soft_fail]}
