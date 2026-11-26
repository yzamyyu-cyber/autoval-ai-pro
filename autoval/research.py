"""AI Research Analyst (read-only).

Consumes a validated analysis snapshot and produces a structured, evidence-grounded research
report. Financial tables are rendered deterministically from the snapshot (never reproduced by
the LLM); the LLM only writes the narrative/interpretation. The agent never modifies financial
inputs, valuation formulas or reconciliation records.
"""
from __future__ import annotations
import json
import re

from .reconciliation import llm as llm_mod

PROMPT_VERSION = "research_v2"
MODEL_VERSION = "deepseek-v4-pro-0813"


def research_cache_key(result: dict) -> dict:
    """Identity of the analysis that a research report must match (shared by website + PDF)."""
    a = result.get("analysis") or {}
    drivers = ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {}
    return {
        "company": result.get("company"),
        "ticker": result.get("ticker"),
        "snapshot": result.get("run_utc"),
        "period": a.get("financial_asof"),
        "basis": result.get("valuation_basis", "annual"),
        "corrections": bool(result.get("reconciled")),
        "drivers": {k: round(v, 6) for k, v in sorted(drivers.items())},
        "market_mode": result.get("market_mode"),
        "prompt_version": PROMPT_VERSION,
        "model_version": MODEL_VERSION,
    }


def validate_research_cache_match(key: dict, meta: dict) -> bool:
    """True only when the cached report identity matches the current analysis identity."""
    for field in ("company", "ticker", "snapshot", "period", "basis", "corrections",
                  "market_mode", "prompt_version", "model_version"):
        if key.get(field) != meta.get(field):
            return False
    if key.get("drivers") != meta.get("drivers"):
        return False
    return True


_FINANCIAL_QUESTIONS = (
    "revenue", "operating_margin", "capex", "fcff", "wacc", "dcf", "risks", "peers",
)


def deterministic_answer(question: str, result: dict) -> dict:
    """Deterministic, source-grounded answer for supported financial questions (no LLM)."""
    a = result.get("analysis") or {}
    base = a.get("scenarios", {}).get("base", {})
    drivers = ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {}
    hist = result.get("forecast_history") or {}
    rev = (hist.get("revenue") or [])
    q = (question or "").strip().lower()
    if q in ("revenue", "revenue growth"):
        g = drivers.get("revenue_growth")
        latest = rev[-1] if rev else None
        return {"answer": (f"Latest FY revenue {_fmt_usd(latest)}; base-case forecast revenue growth "
                           f"{_fmt_pct(g)} (driver-derived, not guidance)."),
                "sources": []}
    if q in ("operating_margin", "margin", "profitability"):
        m = drivers.get("operating_margin")
        return {"answer": f"Base-case operating margin (EBIT/revenue) {_fmt_pct(m)} (trailing-3-year).", "sources": []}
    if q in ("capex", "capex intensity"):
        c = drivers.get("capex_ratio")
        return {"answer": f"CapEx intensity {_fmt_pct(c)} of revenue (driver-derived).", "sources": []}
    if q == "fcff":
        return {"answer": f"Base-case year-1 FCFF {_fmt_usd((a.get('forecast') or {}).get('base', {}).get('rows', [{}])[0].get('fcff'))}.", "sources": []}
    if q == "wacc":
        c = ((result.get("wacc") or {}).get("calculation") or {})
        basis = result.get("wacc_basis")
        return {"answer": f"WACC {_fmt_pct(c.get('wacc'))} ({basis}) = cost of equity "
                          f"{_fmt_pct(c.get('cost_of_equity'))} · after-tax cost of debt "
                          f"{_fmt_pct(c.get('after_tax_cost_of_debt'))} · equity weight {_fmt_pct(c.get('equity_weight'))}.",
                "sources": []}
    if q == "dcf":
        return {"answer": (f"Five-year DCF base {_fmt_usd(base.get('intrinsic_per_share_usd'))}; "
                           f"multi-stage base {_fmt_usd((a.get('multistage') or {}).get('base', {}).get('intrinsic_per_share_usd'))}."),
                "sources": []}
    if q in ("risks", "limitations", "risk"):
        return {"answer": " · ".join(result.get("limitations", [])[:4]) or "No documented limitations.",
                "sources": []}
    if q in ("peers", "peer", "comparable", "industry"):
        rel = result.get("relative")
        if not rel:
            return {"answer": "Peer multiples are unavailable for this snapshot.", "sources": []}
        groups = []
        for gk, g in rel.get("groups", {}).items():
            pe = g.get("pe", {}).get("median_pe"); ev = g.get("ev_ebitda", {}).get("median_ev_ebitda")
            groups.append(f"{gk}: P/E median {pe or '—'}, EV/EBITDA median {ev or '—'}")
        return {"answer": "; ".join(groups), "sources": []}
    return {"answer": None, "sources": []}


def _fmt_usd(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "n/a"


def _fmt_pct(v):
    return f"{v:.1%}" if isinstance(v, (int, float)) else "n/a"


def render_tables(result: dict) -> str:
    """Render the deterministic financial tables (no LLM)."""
    a = result["analysis"]
    cases = a["scenarios"]
    lines = []
    lines.append("## Financial tables (deterministic)")
    lines.append("")
    lines.append("| Scenario | Intrinsic/share | vs price | WACC | FCFF growth | Terminal g |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for case in ("bear", "base", "bull"):
        c = cases[case]
        up = c.get("upside_vs_price_pct")
        up_disp = f"{up:+.1f}%" if up is not None else "n/a"  # already a percentage
        g = c.get("growth")
        gdisp = _fmt_pct(g) if g is not None else "driver"
        lines.append(f"| {case.title()} | {_fmt_usd(c['intrinsic_per_share_usd'])} | {up_disp} | "
                     f"{_fmt_pct(c['wacc'])} | {gdisp} | {_fmt_pct(c['terminal_growth'])} |")
    lines.append("")

    ms = a.get("multistage")
    if ms:
        lines.append("| Scenario | Five-year DCF | Multi-stage DCF |")
        lines.append("|---|---:|---:|")
        for case in ("bear", "base", "bull"):
            if case in ms:
                lines.append(f"| {case.title()} | "
                             f"{_fmt_usd(cases[case]['intrinsic_per_share_usd'])} | "
                             f"{_fmt_usd(ms[case]['intrinsic_per_share_usd'])} |")
        lines.append("")

    drivers = ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {}
    if drivers:
        lines.append("| Driver | Value |")
        lines.append("|---|---:|")
        for k, label in (("revenue_growth", "Revenue growth"), ("operating_margin", "Operating margin"),
                         ("normalized_tax_rate", "Tax rate"), ("da_ratio", "D&A / revenue"),
                         ("capex_ratio", "CapEx / revenue"), ("nwc_ratio", "NWC / revenue")):
            if k in drivers:
                lines.append(f"| {label} | {_fmt_pct(drivers[k])} |")
        lines.append("")

    # Historical financial trends (from the forecast history).
    hist = result.get("forecast_history") or {}
    fy = hist.get("fiscal_years") or []
    rev_h = hist.get("revenue") or []
    op_h = hist.get("operating_income") or []
    cx_h = hist.get("capex") or []
    da_h = hist.get("da") or []
    if fy and rev_h:
        lines.append("| Fiscal year | Revenue | Operating income | Margin | CapEx | D&A |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for i, y in enumerate(fy):
            rev = rev_h[i] if i < len(rev_h) else None
            op = op_h[i] if i < len(op_h) else None
            cx = cx_h[i] if i < len(cx_h) else None
            da = da_h[i] if i < len(da_h) else None
            margin = (op / rev) if (op is not None and rev) else None
            lines.append(f"| {y[:10]} | {_fmt_usd(rev)} | {_fmt_usd(op)} | "
                         f"{_fmt_pct(margin)} | {_fmt_usd(cx)} | {_fmt_usd(da)} |")
        lines.append("")

    # TTM metrics.
    ttm = a.get("ttm") or {}
    ttm_items = [(k, v) for k, v in (("revenue", ttm.get("revenue")),
                                     ("operating_income", ttm.get("operating_income")),
                                     ("operating_cash_flow", ttm.get("operating_cash_flow")),
                                     ("capex", ttm.get("capex")), ("da", ttm.get("da")))
                 if v is not None]
    if ttm_items:
        lines.append("| TTM metric (as of " + str(ttm.get("asof") or "—") + ") | Value |")
        lines.append("|---|---:|")
        for k, v in ttm_items:
            lines.append(f"| {k.replace('_', ' ')} | {_fmt_usd(v)} |")
        lines.append("")

    # Sensitivity grid (WACC x terminal growth).
    sens = a.get("sensitivity")
    if sens:
        lines.append("| WACC | Terminal g | Intrinsic/share |")
        lines.append("|---|---:|---:|")
        for s in sens[:15]:
            lines.append(f"| {_fmt_pct(s.get('wacc'))} | {_fmt_pct(s.get('terminal_growth'))} | "
                         f"{_fmt_usd(s.get('intrinsic_per_share_usd'))} |")
        lines.append("")

    wacc = result.get("wacc") or {}
    if wacc.get("available") and wacc.get("calculation"):
        c = wacc["calculation"]
        lines.append("| WACC input | Value |")
        lines.append("|---|---:|")
        lines.append(f"| Risk-free rate | {_fmt_pct(c.get('risk_free_rate'))} |")
        lines.append(f"| Beta | {c.get('beta', 0):.2f} |")
        lines.append(f"| Equity risk premium | {_fmt_pct(c.get('equity_risk_premium'))} |")
        lines.append(f"| Cost of equity | {_fmt_pct(c.get('cost_of_equity'))} |")
        lines.append(f"| After-tax cost of debt | {_fmt_pct(c.get('after_tax_cost_of_debt'))} |")
        lines.append(f"| Equity weight | {_fmt_pct(c.get('equity_weight'))} |")
        lines.append(f"| **WACC** | **{_fmt_pct(c.get('wacc'))}** |")
        lines.append("")

    rel = result.get("relative")
    if rel:
        lines.append("## Comparable valuation (deterministic)")
        lines.append("")
        for gkey, g in rel.get("groups", {}).items():
            pe = g.get("pe", {}); ev = g.get("ev_ebitda", {})
            lines.append(f"- {gkey}: P/E median {pe.get('median_pe', 'n/a')}, "
                         f"implied {_fmt_usd(pe.get('implied_price_median'))}; "
                         f"EV/EBITDA median {ev.get('median_ev_ebitda', 'n/a')}, "
                         f"implied {_fmt_usd(ev.get('implied_price_median'))}")
        lines.append("")

    ev = result.get("evidence") or []
    if ev:
        lines.append("## Evidence records (deterministic)")
        lines.append("")
        lines.append("| Evidence ID | Metric | Value | Verification |")
        lines.append("|---|---|---:|---|")
        for e in ev[:40]:
            val = e.get("reported_value") or e.get("derived_value")
            vd = f"{val:,.0f}" if isinstance(val, (int, float)) else "—"
            lines.append(f"| `{e['evidence_id']}` | {e.get('metric')} | {vd} | "
                         f"{e.get('verification_status')} |")
        lines.append("")
    return "\n".join(lines)


def _evidence_map(result: dict) -> dict:
    """Map evidence_id -> {metric, value, period_end, units, verification}."""
    out = {}
    for e in (result.get("evidence") or []):
        val = e.get("reported_value") if e.get("reported_value") is not None else e.get("derived_value")
        out[e["evidence_id"]] = {
            "metric": e.get("metric"), "value": val,
            "period_end": e.get("period_end"), "units": e.get("units"),
            "verification": e.get("verification_status"),
        }
    return out


def data_context(result: dict) -> dict:
    """Structured metric map for grounding (definition, period, units, evidence reference)."""
    a = result["analysis"]
    ctx = {"company": result.get("company"), "ticker": result.get("ticker"),
           "snapshot_id": result.get("run_utc"), "market_mode": result.get("market_mode"),
           "wacc_basis": result.get("wacc_basis"),
           "valuation_basis": result.get("valuation_basis", "annual"),
           "quality": (result.get("quality") or {}).get("state"),
           "evidence": _evidence_map(result),
           "scenarios": {c: {"intrinsic_per_share_usd": a["scenarios"][c]["intrinsic_per_share_usd"],
                             "wacc": a["scenarios"][c]["wacc"],
                             "terminal_growth": a["scenarios"][c]["terminal_growth"],
                             "upside_vs_price_pct": a["scenarios"][c].get("upside_vs_price_pct")}
                         for c in ("bear", "base", "bull")},
           "drivers": ((a.get("forecast") or {}).get("base") or {}).get("drivers") or {},
           "forecast_history": result.get("forecast_history") or {},
           "ttm": a.get("ttm") or {},
           "wacc_calc": ((result.get("wacc") or {}).get("calculation") or {}),
           "sensitivity": a.get("sensitivity") or [],
           "relative": result.get("relative"),
           "limitations": result.get("limitations") or [],
           }
    return ctx


def _evidence_ids(result: dict) -> set:
    return {e["evidence_id"] for e in (result.get("evidence") or [])}


def _prompt(result: dict, tables: str) -> str:
    q = result.get("quality") or {}
    evidence = result.get("evidence") or []
    ev_summary = [{"id": e["evidence_id"], "metric": e["metric"], "kind": e.get("kind"),
                   "verification": e.get("verification_status")} for e in evidence[:40]]
    return (
        "You are an equity research analyst. Write a professional research report for the "
        "company below, using ONLY the provided data and evidence. Distinguish REPORTED facts, "
        "DERIVED calculations, ASSUMED parameters and your own INTERPRETATION.\n\n"
        f"COMPANY: {result.get('company')} ({result.get('ticker')})\n"
        f"SNAPSHOT ID: {result.get('run_utc')}\n"
        f"MARKET-DATA MODE: {result.get('market_mode')} · WACC BASIS: {result.get('wacc_basis')}\n"
        f"VALUATION QUALITY: {q.get('state')}\n"
        f"DATA QUALITY: {q.get('data_quality')}\n"
        f"MODEL LIMITATIONS: {q.get('model_suitability')} + {q.get('unsuitability')}\n"
        f"LIMITATIONS: {result.get('limitations')}\n\n"
        "EVIDENCE RECORDS (cite these IDs when making numerical claims):\n"
        + json.dumps(ev_summary, default=str, indent=2) + "\n\n"
        "DETERMINISTIC TABLES (do NOT re-state these numbers as your own; reference them):\n"
        + tables + "\n\n"
        "Return JSON with these keys:\n"
        "- executive_summary\n- business_and_financial_performance\n"
        "- revenue_growth_profitability_reinvestment\n- dcf_interpretation\n"
        "- wacc_and_terminal_assumptions\n- comparable_and_reverse_dcf\n"
        "- valuation_drivers_and_sensitivities\n- risks_and_limitations\n"
        "- evidence_backed_conclusion\n"
        "- claims: a list of {evidence_id, metric, value, period_end} for EVERY numerical "
        "fact you assert (value must exactly match the evidence record)\n"
        "Rules: cite evidence IDs in square brackets like [ticker.metric]; do not invent "
        "business facts, numbers, forecasts or citations; if the valuation is unavailable or "
        "low-confidence, say so and do not present an unsupported headline; never output an "
        "API key."
    )


def build_report(result: dict, chat_fn=None) -> dict:
    """Generate a research report. `chat_fn(messages)` is injectable for tests."""
    chat_fn = chat_fn or (lambda messages: llm_mod.chat(messages))
    tables = render_tables(result)
    prompt = _prompt(result, tables)
    try:
        raw = chat_fn([{"role": "user", "content": prompt}])
        sections = llm_mod.extract_json(raw)
    except Exception as exc:
        sections = {"error": f"LLM unavailable: {exc}"}
    claims = sections.pop("claims", []) if isinstance(sections, dict) else []
    report = {
        "ticker": result.get("ticker"),
        "company": result.get("company"),
        "snapshot_id": result.get("run_utc"),
        "sections": sections,
        "claims": claims,
        "tables": tables,
        "evidence_ids": sorted(_evidence_ids(result)),
        "cache_key": research_cache_key(result),
        "markdown": _compose_markdown(result, sections, tables),
    }
    report["validation"] = validate_report(report, result)
    return report


def answer_question(result: dict, question: str, chat_fn=None) -> dict:
    """Private, evidence-grounded free-text Q&A using the LLM (explicit submission only).

    The prompt is grounded in the selected snapshot's evidence + deterministic tables; the
    answer is validated for claim/citation consistency. Never modifies inputs.
    """
    chat_fn = chat_fn or (lambda messages: llm_mod.chat(messages))
    tables = render_tables(result)
    evidence = [{"id": e["evidence_id"], "metric": e["metric"],
                 "value": e.get("reported_value") if e.get("reported_value") is not None else e.get("derived_value"),
                 "period_end": e.get("period_end"), "verification": e.get("verification_status")}
                for e in (result.get("evidence") or [])[:50]]
    prompt = (
        "You are a financial research assistant. Answer the question using ONLY the provided "
        "evidence and deterministic tables. Do not invent numbers, facts or citations.\n\n"
        f"COMPANY: {result.get('company')} ({result.get('ticker')}) · SNAPSHOT {result.get('run_utc')}\n"
        f"MARKET MODE {result.get('market_mode')} · QUALITY {(result.get('quality') or {}).get('state')}\n"
        "EVIDENCE (id: metric = value @period):\n" + json.dumps(evidence, default=str, indent=2) +
        "\n\nDETERMINISTIC TABLES:\n" + tables + "\n\n"
        f"QUESTION: {question}\n\n"
        "Return JSON with keys:\n- answer (string)\n"
        "- claims: [{'evidence_id', 'value', 'period_end'}] for every numerical fact you assert\n"
        "- sources: [evidence ids you cite]\n"
        "If the evidence is insufficient, say so in `answer` and return empty claims. Never output an API key."
    )
    try:
        raw = chat_fn([{"role": "user", "content": prompt}])
        parsed = llm_mod.extract_json(raw)
    except Exception as exc:
        return {"answer": None, "error": f"LLM unavailable: {exc}", "validation": {"status": "unresolved"}}
    answer = parsed.get("answer") if isinstance(parsed, dict) else None
    claims = parsed.get("claims", []) if isinstance(parsed, dict) else []
    validation = validate_answer_claims(claims, result)
    return {"answer": answer, "claims": claims, "sources": parsed.get("sources", []),
            "validation": validation}


def validate_answer_claims(claims: list[dict], result: dict) -> dict:
    """Validate the numeric claims/citations in a Q&A answer (reuses the evidence map)."""
    emap = _evidence_map(result)
    mismatches = []
    for c in claims:
        eid = c.get("evidence_id"); rec = emap.get(eid)
        if rec is None:
            mismatches.append(f"{eid}: unknown evidence id"); continue
        if c.get("metric") and c["metric"] != rec["metric"]:
            mismatches.append(f"{eid}: metric mismatch")
        cv = c.get("value"); rv = rec.get("value")
        if cv is not None and isinstance(rv, (int, float)) and isinstance(cv, (int, float)):
            if abs(cv - rv) > max(1.0, abs(rv) * 0.01):
                mismatches.append(f"{eid}: value mismatch ({cv} vs {rv})")
        if c.get("period_end") and rec.get("period_end") and c["period_end"] != rec["period_end"]:
            mismatches.append(f"{eid}: period mismatch")
    return {"status": "validated" if not mismatches else "rejected",
            "mismatches": mismatches}


def _compose_markdown(result: dict, sections: dict, tables: str) -> str:
    if not isinstance(sections, dict):
        return "# Research report unavailable\n\n" + str(sections)
    labels = [
        ("executive_summary", "Executive summary"),
        ("business_and_financial_performance", "Business and financial performance"),
        ("revenue_growth_profitability_reinvestment", "Revenue growth, profitability and reinvestment"),
        ("dcf_interpretation", "Five-year vs multi-stage DCF"),
        ("wacc_and_terminal_assumptions", "WACC and terminal-value assumptions"),
        ("comparable_and_reverse_dcf", "Comparable valuation and reverse DCF"),
        ("valuation_drivers_and_sensitivities", "Key valuation drivers and sensitivities"),
        ("risks_and_limitations", "Financial risks and model limitations"),
        ("evidence_backed_conclusion", "Research conclusion"),
    ]
    lines = [f"# {result.get('company')} ({result.get('ticker')}) — Research Report", ""]
    for key, label in labels:
        body = sections.get(key)
        if body:
            lines.append(f"## {label}")
            lines.append(str(body).strip())
            lines.append("")
    lines.append(tables)
    return "\n".join(lines)


def validate_report(report: dict, result: dict) -> dict:
    """Validate the report's cited evidence IDs and company/snapshot identity."""
    checks = []
    sections = report.get("sections") or {}
    cited = set()
    if isinstance(sections, dict):
        for v in sections.values():
            if isinstance(v, str):
                cited |= set(re.findall(r"\[([A-Za-z0-9_.]+)\]", v))
    valid_ids = _evidence_ids(result)
    unknown = sorted(cited - valid_ids)
    checks.append({"check": "evidence_ids_exist", "ok": not unknown,
                   "reason": f"unknown cited IDs: {unknown}" if unknown else "all cited IDs exist"})
    checks.append({"check": "identity", "ok": report.get("ticker") == result.get("ticker"),
                   "reason": "ticker matches" if report.get("ticker") == result.get("ticker") else "ticker mismatch"})
    checks.append({"check": "snapshot_identity",
                   "ok": report.get("snapshot_id") == result.get("run_utc"),
                   "reason": ("snapshot matches" if report.get("snapshot_id") == result.get("run_utc")
                              else "stale snapshot: report was generated against a different snapshot")})
    # Reject fabricated narrative: the LLM must not invent a headline valuation when the
    # model is unavailable/low-confidence.
    q = (result.get("quality") or {}).get("state")
    conclusion = (sections.get("evidence_backed_conclusion") or "") if isinstance(sections, dict) else ""
    unsupported = (q in ("unavailable", "low_confidence") and
                   re.search(r"\$\d[\d,]*\s*per share", conclusion or ""))
    checks.append({"check": "no_unsupported_headline", "ok": not unsupported,
                   "reason": ("suppressed" if not unsupported else "headline suppressed for unsupported model")})

    # Structured financial claims: an evidence ID alone is not proof of correctness. Each
    # claim must bind to the actual supporting value (metric + value + period).
    emap = _evidence_map(result)
    claims = report.get("claims") or []
    claim_mismatches = []
    for cl in claims:
        eid = cl.get("evidence_id")
        rec = emap.get(eid)
        if rec is None:
            claim_mismatches.append(f"{eid}: unknown evidence id")
            continue
        if cl.get("metric") and cl["metric"] != rec["metric"]:
            claim_mismatches.append(f"{eid}: metric mismatch ({cl['metric']} vs {rec['metric']})")
        cv = cl.get("value")
        rv = rec.get("value")
        if cv is not None and isinstance(rv, (int, float)) and isinstance(cv, (int, float)):
            tol = max(1.0, abs(rv) * 0.01)
            if abs(cv - rv) > tol:
                claim_mismatches.append(f"{eid}: value mismatch ({cv} vs {rv})")
        if cl.get("period_end") and rec.get("period_end") and cl["period_end"] != rec["period_end"]:
            claim_mismatches.append(f"{eid}: period mismatch ({cl['period_end']} vs {rec['period_end']})")
    checks.append({"check": "structured_claims", "ok": not claim_mismatches,
                   "reason": f"claim mismatches: {claim_mismatches}" if claim_mismatches else "structured claims consistent"})

    ok = all(c["ok"] for c in checks)
    return {"status": "validated" if ok else "rejected", "checks": checks}
