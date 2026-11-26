#!/usr/bin/env python3
"""Phase 2D.2 — LLM-assisted D&A recovery for Nike and Alphabet.

Retrieves the original consolidated cash-flow statement inline-XBRL facts, asks the LLM to
identify the correct D&A line / non-overlapping reconstruction, and records the finding
alongside the deterministic `da.py` result. Benchmarks are NOT passed to the LLM.

Usage:
    SEC_USER_AGENT="App contact@example.com" .venv/bin/python evidence/phase2d2_da_agent.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.sec import sec_lookup, fetch_json, FACTS_URL
from autoval.reconciliation import llm as llm_mod, save_record
from autoval.reconciliation import retrieve as rec_retrieve
from autoval.reconciliation import filing as filing_mod
from autoval.da import resolve_annual_da
from autoval.forecast_data import retrieve_history

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")

DEFAULTS = {
    "NKE": {"accession": "0000320187-26-000088", "form": "10-K",
            "filing_url": "https://www.sec.gov/Archives/edgar/data/320187/000032018726000088/nke-20260531.htm"},
    "GOOGL": {"accession": "0001652044-26-000018", "form": "10-K",
              "filing_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm"},
}

DA_TAGS = ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet", "Depreciation",
           "AmortizationOfIntangibleAssets", "FinanceLeaseRightOfUseAssetAmortization")


def prompt(ticker, filing_url, inline_facts, deterministic):
    return (
        "You are an accounting analyst reconciling depreciation & amortization (D&A) from "
        f"{ticker}'s original consolidated cash-flow statement.\n\n"
        "DETERMINISTIC RESOLVER RESULT:\n" + json.dumps(deterministic, default=str, indent=2) +
        "\n\nORIGINAL-FILING INLINE XBRL D&A FACTS (exact values, units, scale, sign, period):\n"
        + json.dumps(inline_facts, default=str, indent=2) +
        "\n\nIdentify the correct consolidated D&A line and the non-overlapping component "
        "reconstruction. Confirm whether Depreciation is a complete D&A figure or only PP&E "
        "depreciation, and whether finance-lease ROU amortization must be added separately. "
        "Return JSON with keys: 'da_tag' (the consolidated tag, or 'component_sum'), "
        "'reconstruction' (list of component tags to sum, non-overlapping), "
        "'explanation' (short), 'remaining_uncertainty' (short). Do not invent values."
    )


def run(ticker, ua):
    cik, name = sec_lookup(ticker, ua)
    facts = fetch_json(FACTS_URL.format(cik=cik), ua)
    hist = retrieve_history(ticker, ua)
    years = hist["fiscal_years"]
    deterministic = resolve_annual_da(facts, years)

    default = DEFAULTS[ticker]
    try:
        filing = rec_retrieve.latest_periodic(cik, ua, forms=("10-K",))
        url = (rec_retrieve.filing_url(cik, filing["accession"], filing["primary_document"])
               if filing else default["filing_url"])
    except Exception:
        url = default["filing_url"]

    inline_facts = {}
    try:
        ev = filing_mod.filing_evidence(url, ua, DA_TAGS,
                                        period=years[-1],
                                        note_keywords=("depreciation", "amortization"))
        inline_facts = {t: (v.get("value") if v else None) for t, v in ev.get("facts", {}).items()}
    except Exception as exc:
        inline_facts = {"error": str(exc)}

    raw = llm_mod.chat([{"role": "user", "content": prompt(ticker, url, inline_facts, deterministic)}])
    parsed = llm_mod.extract_json(raw)
    record = {
        "ticker": ticker, "company": name, "category": "da_recovery",
        "detected_problem": "D&A was unavailable; recover from the original cash-flow statement.",
        "filing_url": url, "filing_accession": (filing or default).get("accession") if filing else default["accession"],
        "inline_facts": inline_facts,
        "deterministic_da": {"status": deterministic["status"],
                             "values": deterministic["values"],
                             "detail": deterministic["detail"]},
        "llm_da_tag": parsed.get("da_tag"),
        "llm_reconstruction": parsed.get("reconstruction"),
        "llm_explanation": parsed.get("explanation"),
        "remaining_uncertainty": parsed.get("remaining_uncertainty"),
        "deterministic_validation": {"status": "validated" if deterministic["status"] != "unavailable" else "unresolved",
                                     "checks": []},
        "approval_status": "pending",
    }
    save_record(record, RECORDS_DIR)
    return record


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    out = []
    for ticker in ("NKE", "GOOGL"):
        try:
            out.append(run(ticker, ua))
        except Exception as exc:
            out.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
