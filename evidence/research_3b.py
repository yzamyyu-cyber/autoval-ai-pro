#!/usr/bin/env python3
"""Phase 3B — two actual research runs (MSFT comprehensive + WMT corrected). 2 LLM calls."""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from autoval.research import build_report


def msft_case():
    from tests.provider_fixture import build_from_fixture
    return build_from_fixture("MSFT")[0]


def wmt_case(ua):
    from autoval.sec import get_sec_financials
    from autoval.forecast_data import retrieve_history
    from autoval.finance import analyze_driver_valuation
    from autoval.reconciliation import apply_correction, load_record, list_records
    from autoval.quality import assess_valuation_quality
    from autoval.provenance import build_provenance
    stock = get_sec_financials("WMT", ua)
    rec = None
    for p in reversed(list_records(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "reconciliation_records"))):
        if os.path.basename(p).startswith("WMT_"):
            rec = load_record(p)
            break
    corrected = apply_correction(stock, rec)["corrected"] if rec else stock
    history = retrieve_history("WMT", ua)
    valuation = analyze_driver_valuation(corrected, history, None)
    result = {"project": "AutoVal AI Pro", "run_utc": "2026-11-25T00:00:00Z", "mode": "live",
              "company": corrected.get("company", "Walmart Inc."), "ticker": "WMT",
              "analysis": valuation, "wacc": {"available": False, "inputs": {}},
              "forecast_history": history, "forecast_basis": "driver", "relative": None,
              "provenance": {"financials": corrected.get("source", {}),
                             "market": {"provider": "illustrative"}},
              "market_mode": "illustrative", "wacc_basis": "illustrative",
              "reconciled": True, "limitations": valuation["limitations"]}
    result["quality"] = assess_valuation_quality(result)
    result["evidence"] = build_provenance(result)
    return result


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    out = {}
    for ticker, result in (("MSFT", msft_case()), ("WMT", wmt_case(ua))):
        report = build_report(result)
        base = result["analysis"]["scenarios"]["base"]
        out[ticker] = {
            "quality": result["quality"]["state"],
            "base_intrinsic": base["intrinsic_per_share_usd"],
            "base_equity": base["equity_value_usd"],
            "validation": report["validation"]["status"],
            "n_claims": len(report.get("claims") or []),
            "checks": [(c["check"], c["ok"]) for c in report["validation"]["checks"]],
        }
        with open(f"evidence/research_report_{ticker.lower()}_3b.md", "w", encoding="utf-8") as f:
            f.write(report.get("markdown", ""))
    with open("evidence/research_cases_3b.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
