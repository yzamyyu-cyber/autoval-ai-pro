"""Peer universe and screening. Config-driven; no ticker-specific logic in the
general functions. MSFT's mapping is data, not code."""

# Company-specific comparative notes (used for disclosures, not in the math).
PEER_NOTES = {
    "SAP": "IFRS reporter (EUR); ADR ratio 1:1 (SAP SE NYSE-listed ADS); Dec fiscal year-end. "
           "IFRS 16 lease treatment must be normalized before primary EV/EBITDA inclusion.",
    "NOW": "Enterprise ITSM/workflow SaaS; materially smaller market cap and faster growth than MSFT.",
    "CRM": "Pure enterprise SaaS (no IaaS); Jan fiscal year-end.",
    "ADBE": "Enterprise software with creative skew; Nov fiscal year-end.",
    "ORCL": "Database/ERP + OCI cloud; Jun fiscal year-end (aligns with MSFT).",
    "AMZN": "AWS competes with Azure but retail dominates (~5-10% margin vs MSFT ~45%).",
    "GOOGL": "Google Cloud competes with Azure but Search/ads dominate (~30% margin).",
}

# Industry -> peer groups. Case-insensitive ticker keys in TICKER_INDUSTRY.
TICKER_INDUSTRY = {
    "MSFT": "software",
}

INDUSTRY_PEER_GROUPS = {
    "software": {
        "core_software": ["ORCL", "CRM", "ADBE"],
        "supplemental_software": ["NOW", "SAP"],
        "cloud_platform": ["AMZN", "GOOGL"],
    },
}

META = {
    "software": {
        "core_software": {"label": "Core software peers", "primary": True},
        "supplemental_software": {"label": "Supplemental software peers", "primary": True,
                                  "note": "Reported separately; NOW differs on size/growth."},
        "cloud_platform": {"label": "Secondary cloud/platform peers", "primary": False,
                           "note": "Different business mix; reported separately, not blended."},
    },
}

# Fields a peer must have to be considered valid (for screening).
REQUIRED_FIELDS = ("market_cap", "ttm_eps", "ttm_ebitda", "ev")


def peer_groups(ticker: str) -> dict:
    """Return {group_key: [tickers]} for a ticker's industry, else {}."""
    industry = TICKER_INDUSTRY.get(ticker.upper(), "unknown")
    return INDUSTRY_PEER_GROUPS.get(industry, {})


def screen_peers(peers: dict, min_valid: int = 3) -> dict:
    """Screen a {ticker: peer_dict} mapping by data availability and validity.

    Returns {"valid": {ticker: peer_dict}, "excluded": [{ticker, reason}, ...]}.
    A peer is invalid if missing REQUIRED_FIELDS or has non-meaningful
    (negative/zero) trailing EPS and EBITDA.
    """
    valid = {}
    excluded = []
    for ticker, data in peers.items():
        missing = [f for f in REQUIRED_FIELDS if data.get(f) in (None, float("nan"))]
        if missing:
            excluded.append({"ticker": ticker, "reason": f"missing {', '.join(missing)}"})
            continue
        if not data.get("valued"):
            excluded.append({"ticker": ticker, "reason": "not valued (data unavailable/stale)"})
            continue
        valid[ticker] = data
    return {"valid": valid, "excluded": excluded}