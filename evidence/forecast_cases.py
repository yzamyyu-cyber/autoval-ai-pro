#!/usr/bin/env python3
"""Phase 5 — evidence-backed forecast assumptions (AMZN + MSFT). 2 LLM calls."""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from tests.provider_fixture import build_from_fixture
from autoval.forecast_assumptions import investigate_assumptions, validate_assumptions


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        print("Set SEC_USER_AGENT")
        return 1
    out = {}
    for ticker in ("AMZN", "MSFT"):
        result, _ = build_from_fixture(ticker)
        inv = investigate_assumptions(result, ua)
        validation = validate_assumptions(inv.get("proposals", []), result)
        out[ticker] = {
            "quality": result["quality"]["state"],
            "validation": validation["status"],
            "proposals": inv.get("proposals"),
            "current": inv.get("current"),
            "filing_accession": inv.get("excerpts", {}).get("accession"),
        }
        with open(f"evidence/forecast_proposals_{ticker.lower()}.json", "w", encoding="utf-8") as f:
            json.dump(out[ticker], f, indent=2, default=str)
    with open("evidence/forecast_cases.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps({t: {"validation": v["validation"],
                          "n_proposals": len(v["proposals"] or []),
                          "drivers": [p.get("driver") for p in (v["proposals"] or [])]}
                      for t, v in out.items()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
