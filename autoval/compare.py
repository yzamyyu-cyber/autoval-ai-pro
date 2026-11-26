"""Compare saved AutoVal analyses without fetching provider data."""
from __future__ import annotations

import csv
import io
from math import isfinite

from .reverse import reverse_dcf


def extract_comparison(result: dict) -> dict:
    """Extract a common set of fields from an AutoVal analysis export."""
    analysis = result["analysis"]
    base = analysis["scenarios"]["base"]
    price = analysis["market_price"]
    intrinsic = base["intrinsic_per_share_usd"]
    if not (isfinite(price) and price > 0 and isfinite(intrinsic)):
        raise ValueError("A comparison requires a positive price and a finite base DCF.")
    if result["mode"] not in ("demo", "live"):
        raise ValueError("An analysis must identify whether its data mode is demo or live.")

    driver = analysis.get("forecast")
    growth = driver["base"]["drivers"].get("revenue_growth") if driver else base.get("growth")
    groups = (result.get("relative") or {}).get("groups", {})
    group_name = "core_software" if "core_software" in groups else next(iter(groups), None)
    group = groups.get(group_name) or {}
    enough_peers = group.get("sample_size", 0) >= 3
    currency = analysis.get("currency") or "USD"
    implied = None
    if currency == "USD":
        try:
            implied = reverse_dcf(result)["implied_fcff_growth"]
        except (KeyError, TypeError, ValueError):
            # Older exports and some valid valuations lack a usable reverse DCF.
            pass

    # Valuation quality is optional on older exports: absence must be labeled
    # "Not assessed" (never implied to have passed the quality policy).
    quality = result.get("quality") or {}
    quality_state = quality.get("state") or "not_assessed"
    quality_reasons = "; ".join(quality.get("reasons") or []) or None

    return {
        "ticker": result["ticker"],
        "company": result["company"],
        "mode": result["mode"],
        "currency": currency,
        "price": price,
        "price_date": analysis.get("price_date"),
        "financial_asof": analysis.get("financial_asof"),
        "base_dcf_per_share": intrinsic,
        "intrinsic_price_gap_usd": intrinsic - price if currency == "USD" else None,
        "valuation_gap_pct": (intrinsic / price - 1) * 100,
        "wacc": base.get("wacc"),
        "wacc_basis": analysis.get("wacc_basis"),
        "forecast_growth": growth,
        "forecast_growth_basis": "Revenue (driver)" if driver else "FCFF (constant-growth)",
        "implied_fcff_growth": implied,
        "peer_group": group_name,
        "peer_sample_size": group.get("sample_size"),
        "median_pe": group["pe"].get("median_pe") if enough_peers else None,
        "median_ev_ebitda": group["ev_ebitda"].get("median_ev_ebitda") if enough_peers else None,
        "quality_state": quality_state,
        "quality_reasons": quality_reasons,
    }


def comparison_rows(results: list[dict]) -> list[dict]:
    return [extract_comparison(result) for result in results]


def comparability_flags(rows: list[dict]) -> list[str]:
    """Flag differences that affect how the two reports can be read together."""
    checks = (
        ("mode", "Data modes differ"),
        ("currency", "Currencies differ"),
        ("financial_asof", "Reporting periods differ"),
        ("price_date", "Price dates differ"),
        ("forecast_growth_basis", "Forecast growth measures differ"),
        ("wacc_basis", "WACC estimation bases differ"),
    )
    flags = []
    for field, label in checks:
        values = {str(row[field]) for row in rows if row.get(field)}
        if len(values) > 1:
            flags.append(f"{label} · {', '.join(sorted(values))}")
    return flags


def comparison_csv(results: list[dict]) -> str:
    """Serialize the same unrounded values read by the comparison table."""
    rows = comparison_rows(results)
    if not rows:
        return ""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: f"'{value}" if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
            for key, value in row.items()
        })
    return buffer.getvalue()
