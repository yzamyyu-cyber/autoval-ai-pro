#!/usr/bin/env python3
"""Phase 3A — three actual AI Research Analyst cases (mocked-safe, 3 LLM calls max).

MSFT (available), WMT (accounting correction), ORCL (unavailable/limited headline).
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from tests.provider_fixture import build_from_fixture
from autoval.research import build_report
from autoval.reconciliation import save_record

RECORDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reconciliation_records")


def msft_case():
    result, _ = build_from_fixture("MSFT")
    return result


def wmt_case(ua):
    from autoval.sec import get_sec_financials
    from autoval.forecast_data import retrieve_history
    from autoval.finance import analyze_driver_valuation
    from autoval.reconciliation import apply_correction, load_record, list_records
    stock = get_sec_financials("WMT", ua)
    rec = None
    for p in reversed(list_records(RECORDS_DIR)):
        if os.path.basename(p).startswith("WMT_"):
            rec = load_record(p)
            break
    corrected = apply_correction(stock, rec)["corrected"] if rec else stock
    history = retrieve_history("WMT", ua)
    valuation = analyze_driver_valuation(corrected, history, None)
    from autoval.quality import assess_valuation_quality
    from autoval.provenance import build_provenance
    result = {"project": "AutoVal AI Pro", "run_utc": "2026-11-25T00:00:00Z", "mode": "live",
              "company": corrected.get("company", "Walmart Inc."), "ticker": "WMT",
              "analysis": valuation, "wacc": {"available": False, "inputs": {}},
              "forecast_basis": "driver", "relative": None,
              "provenance": {"financials": corrected.get("source", {}),
                             "market": {"provider": "illustrative"}},
              "market_mode": "illustrative", "wacc_basis": "illustrative",
              "reconciled": True, "limitations": valuation["limitations"]}
    result["quality"] = assess_valuation_quality(result)
    result["evidence"] = build_provenance(result)
    return result


def orcl_case(ua):
    from autoval.sec import get_sec_financials
    from autoval.forecast_data import retrieve_history
    from autoval.finance import analyze_driver_valuation
    from autoval.quality import assess_valuation_quality
    from autoval.provenance import build_provenance
    stock = get_sec_financials("ORCL", ua)
    history = retrieve_history("ORCL", ua)
    valuation = analyze_driver_valuation(stock, history, None)
    result = {"project": "AutoVal AI Pro", "run_utc": "2026-11-25T00:00:00Z", "mode": "live",
              "company": stock.get("company", "Oracle Corp"), "ticker": "ORCL",
              "analysis": valuation, "wacc": {"available": False, "inputs": {}},
              "forecast_basis": "driver", "relative": None,
              "provenance": {"financials": stock.get("source", {}),
                             "market": {"provider": "illustrative"}},
              "market_mode": "illustrative", "wacc_basis": "illustrative",
              "limitations": valuation["limitations"]}
    result["quality"] = assess_valuation_quality(result)
    result["evidence"] = build_provenance(result)
    return result


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    cases = [("MSFT", msft_case()), ("WMT", wmt_case(ua)), ("ORCL", orcl_case(ua))]
    out = {}
    for ticker, result in cases:
        report = build_report(result)
        out[ticker] = {
            "quality": result["quality"]["state"],
            "validation": report["validation"]["status"],
            "sections": {k: (v if k != "evidence_backed_conclusion" else str(v)[:300])
                         for k, v in (report.get("sections") or {}).items()},
            "markdown_len": len(report.get("markdown", "")),
        }
        with open(f"evidence/research_report_{ticker.lower()}.md", "w", encoding="utf-8") as f:
            f.write(report.get("markdown", ""))
    with open("evidence/research_cases.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
