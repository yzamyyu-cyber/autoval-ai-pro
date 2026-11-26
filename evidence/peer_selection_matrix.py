#!/usr/bin/env python3
"""Phase 4 — automatic peer-selection validation matrix (deterministic + SIC lookup)."""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autoval.peers import discover_peers, get_company_sic

MATRIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peer_selection_matrix.json")
TICKERS = ("MSFT", "AMZN", "AAPL", "WMT", "NKE", "ORCL")


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip() or ""
    rows = []
    for t in TICKERS:
        d = discover_peers(t, ua)
        rows.append({
            "ticker": t,
            "method": d["method"],
            "industry": d.get("industry"),
            "sic": d.get("sic"),
            "sic_description": d.get("sic_description"),
            "groups": {k: {"tickers": v["tickers"], "rationale": v["rationale"]}
                       for k, v in d.get("groups", {}).items()},
            "excluded": d.get("excluded", []),
        })
    # unmapped demonstration (mocked SIC universe — no live lookup of unknown tickers)
    rows.append({
        "ticker": "UNMAPPED_FIXTURE",
        "method": "sic (fixture)",
        "note": "discover_peers falls back to SIC discovery for unmapped tickers; covered by "
                "tests/test_peer_selection.py::test_unmapped_sic_discovery",
    })
    with open(MATRIX, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
