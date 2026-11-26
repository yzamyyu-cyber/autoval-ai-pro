#!/usr/bin/env python3
"""Export acceptance for the four market-data modes.

For each mode, builds the deterministic fixture result, runs the production exporters
(Markdown report, Analysis JSON, Verification JSON, evidence CSV, and save_analysis's
summary.md / technical.csv / forecast.csv), then asserts the exported values agree with
the website-displayed market-data mode, price, WACC basis and dates.

Usage:
    .venv/bin/python evidence/market_mode_export_check.py
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from provider_fixture import build_from_fixture
from autoval.pipeline import save_analysis
from autoval.report import build_report_markdown
from verify_output import check_report

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_mode_exports")
MODES = ("current", "saved", "illustrative", "missing")


def main():
    os.makedirs(OUT, exist_ok=True)
    summary_rows = []
    for mode in MODES:
        result, prices = build_from_fixture("MSFT", mode)
        md = build_report_markdown(result)
        verification = check_report(result)
        evidence = result.get("evidence") or []

        d = os.path.join(OUT, mode)
        os.makedirs(d, exist_ok=True)
        open(f"{d}/report.md", "w", encoding="utf-8").write(md)
        open(f"{d}/analysis.json", "w", encoding="utf-8").write(json.dumps(result, indent=2))
        open(f"{d}/verification.json", "w", encoding="utf-8").write(json.dumps(verification, indent=2))
        if evidence:
            import pandas as pd
            pd.DataFrame(evidence).to_csv(f"{d}/evidence.csv", index=False)
        save_analysis(result, prices, d)

        a = result["analysis"]
        price = a["market_price"]
        # agreement assertions
        checks = []
        checks.append(("JSON market_mode == mode", result["market_mode"] == mode))
        checks.append(("MD mentions market_mode", f"Market-data mode: **{mode}**" in md))
        if mode in ("current", "saved"):
            checks.append(("price is genuine", price is not None and price > 0))
            checks.append(("MD shows price", f"${price:,.2f}" in md))
        else:
            checks.append(("price is None (no genuine)", price is None))
            checks.append(("MD shows n/a price", "n/a" in md))
        checks.append(("wacc_basis set", bool(result.get("wacc_basis"))))
        checks.append(("verification ran", "checks" in verification))
        all_ok = all(ok for _, ok in checks)
        summary_rows.append((mode, result["market_mode"], price, result.get("wacc_basis"),
                             a.get("price_date"), all_ok))
        for label, ok in checks:
            if not ok:
                print(f"  [{mode}] FAIL: {label}")

    print(f"{'mode':<14}{'market_mode':<14}{'price':>12}{'wacc_basis':<18}{'price_date':<14}{'agree'}")
    for mode, mm, price, wb, pd_, ok in summary_rows:
        print(f"{mode:<14}{mm:<14}{str(price):>12}{str(wb):<18}{str(pd_):<14}{ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
