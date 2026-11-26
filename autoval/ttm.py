"""Trailing-twelve-month (TTM) financial extraction (reusable, additive).

TTM is computed from cumulative year-to-date SEC facts as:

    TTM = latest completed fiscal year + current YTD − prior-year-comparable YTD

Robust to issuers that (a) report only the annual total in the 10-K (no single-quarter
Q4), (b) report income-statement items on a cumulative year-to-date basis in each 10-Q,
(c) also disclose a separate rolling 12-month "trailing" figure in the 10-Q (excluded),
and (d) use 52/53-week fiscal calendars whose quarter boundaries shift by a few days.
A single quarter is never treated as full-year and one quarter is never multiplied by
four. Amended filings use the freshest `filed`.
"""
from __future__ import annotations
from datetime import date

from .sec import annual_values, concept


def _cumulative_ytd_facts(facts, tags, unit, today):
    """Cumulative year-to-date 10-Q facts.

    A fact is cumulative YTD when its duration spans more than one quarter but less
    than ~a year (100 < days < 360: excludes single-quarter ~90d and rolling 12-month
    ~364d), or when it is the first fiscal quarter (75-100 days) whose start sits within
    a few days of the fiscal-year start (handles 52/53-week start shifts)."""
    annual = annual_values(facts, tags, unit=unit, today=today)
    if not annual:
        return []
    ref = date.fromisoformat(annual[max(annual)]["start"])
    ref_md = date(2000, ref.month, ref.day)

    out = []
    for tag in tags:
        for item in concept(facts, "us-gaap", tag, unit):
            if item.get("form") not in ("10-Q", "10-Q/A"):
                continue
            if not item.get("start") or not item.get("end") or not item.get("filed"):
                continue
            if item["filed"] > today:
                continue
            try:
                s = date.fromisoformat(item["start"])
                e = date.fromisoformat(item["end"])
            except ValueError:
                continue
            days = (e - s).days
            cumulative = False
            if 100 < days < 360:
                cumulative = True
            elif 75 <= days <= 100:
                s_md = date(2000, s.month, s.day)
                cumulative = abs((s_md - ref_md).days) <= 6
            if cumulative:
                out.append({"value": float(item["val"]), "end": item["end"],
                            "start": item["start"], "filed": item["filed"],
                            "tag": tag, "form": item["form"], "days": days})
    return out


def trailing_twelve_months(facts: dict, tags: tuple, unit: str = "USD",
                           today: str | None = None) -> dict | None:
    """Return {value, fy_end, ytd_end, basis} or None when it cannot be reconciled.

    `basis` is "ttm" when newer quarterly data is used, "annual" when only the latest
    completed fiscal year is available. Returns None when a TTM is needed but the
    prior-year comparable YTD is missing (never fabricates a value).
    """
    today = today or date.today().isoformat()
    annual = annual_values(facts, tags, unit=unit, today=today)
    if not annual:
        return None
    fy_end = max(annual)
    fy = annual[fy_end]["value"]
    # Use the SAME tag that produced the latest annual figure, so the YTD is comparable
    # (handles tag migrations where an issuer moves between e.g. `Revenues` and
    # `RevenueFromContractWithCustomerExcludingAssessedTax`).
    fy_tag = annual[fy_end].get("tag", tags[0])

    ytds = _cumulative_ytd_facts(facts, (fy_tag,), unit, today)
    current = max(ytds, key=lambda x: (x["end"], x["filed"])) if ytds else None
    if current is None or current["end"] <= fy_end:
        return {"value": fy, "fy_end": fy_end, "ytd_end": None, "basis": "annual"}

    prior = _prior_comparable(ytds, current)
    if prior is None:
        return None

    value = fy + current["value"] - prior["value"]
    return {"value": value, "fy_end": fy_end, "ytd_end": current["end"], "basis": "ttm"}


def _prior_comparable(ytds, current):
    """The prior-year-comparable cumulative YTD: the fact in the PRIOR fiscal year
    (end before the current fiscal-year start) with the SAME duration (same quarter
    position), tolerant of 52/53-week shifts (±15 days)."""
    cur_start = date.fromisoformat(current["start"])
    cur_days = current.get("days")
    best = None
    for y in ytds:
        if y is current:
            continue
        y_end = date.fromisoformat(y["end"])
        if y_end >= cur_start:
            continue  # not a prior fiscal year
        if cur_days is not None and y.get("days") is not None:
            if abs(y["days"] - cur_days) > 15:
                continue  # different quarter position
        if best is None or y["end"] > best["end"]:
            best = y
    return best
