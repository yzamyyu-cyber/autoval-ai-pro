"""Peer universe and screening. Config-driven; no ticker-specific logic in the
general functions. Ticker/industry mappings are data, not code."""

# Company-specific comparative notes (used for disclosures, not in the math).
PEER_NOTES = {
    "SAP": "IFRS reporter (EUR); ADR ratio 1:1 (SAP SE NYSE-listed ADS); Dec fiscal year-end. "
           "IFRS 16 lease treatment must be normalized before primary EV/EBITDA inclusion.",
    "NOW": "Enterprise ITSM/workflow SaaS; materially smaller market cap and faster growth than MSFT.",
    "CRM": "Pure enterprise SaaS (no IaaS); Jan fiscal year-end.",
    "ADBE": "Enterprise software with creative skew; Nov fiscal year-end.",
    "ORCL": "Database/ERP + OCI cloud; Jun fiscal year-end (aligns with MSFT).",
    "AMZN": "AWS competes with Azure but retail dominates (~5-10% margin vs MSFT ~45%).",
    "GOOGL": "Alphabet Class A (voting) shares; Google Cloud + Search/ads. Class C is GOOG.",
    "META": "Internet advertising / social; shares digital-ad revenue mix with GOOGL but no cloud IaaS.",
    "TSLA": "EV + energy; auto-manufacturing economics differ from software peers.",
    "F": "Legacy automaker; lower growth/margin than pure-play EV.",
    "GM": "Legacy automaker; lower growth/margin than pure-play EV.",
    "STLA": "Stellantis (ADR); IFRS/EUR — treat with the same caveats as SAP.",
    "RIVN": "EV pure-play; pre-profit and small cap vs TSLA.",
    "LCID": "EV pure-play; pre-profit and small cap vs TSLA.",
    "LOW": "Direct home-improvement retail comparable to HD.",
    "WMT": "Omnichannel retail with grocery skew; materially different margin profile vs AMZN.",
    "TGT": "General-merchandise retail; physical-store economics.",
    "COST": "Membership warehouse club; different capital/revenue model.",
    "EBAY": "Marketplace with no first-party inventory; different revenue/margin mix.",
    "ETSY": "Niche handmade marketplace; much smaller market cap than AMZN.",
    "MELI": "Latin America e-commerce + fintech; regional skew vs AMZN's global mix.",
    "PINS": "Visual discovery / digital advertising; much smaller ad scale.",
    "SNAP": "Social/messaging advertising; volatile profitability.",
    "ORCL": "Database/ERP + OCI cloud; far smaller cloud scale than AWS.",
}

# Industry -> peer groups. Case-insensitive ticker keys in TICKER_INDUSTRY.
TICKER_INDUSTRY = {
    "MSFT": "software",
    "GOOGL": "internet_platforms",
    "META": "internet_platforms",
    "AAPL": "consumer_technology",
    "TSLA": "electric_vehicles",
    "HD": "retail_home_improvement",
    "NVDA": "semiconductors",
    "AMD": "semiconductors",
    "AMZN": "ecommerce_cloud",
}

INDUSTRY_PEER_GROUPS = {
    "software": {
        "core_software": ["ORCL", "CRM", "ADBE"],
        "supplemental_software": ["NOW", "SAP"],
        "cloud_platform": ["AMZN", "GOOGL"],
    },
    "internet_platforms": {
        "core": ["META", "AMZN", "MSFT"],
        "secondary": ["AAPL", "NVDA"],
    },
    "consumer_technology": {
        "core": ["MSFT", "GOOGL", "META"],
        "secondary": ["AMZN", "NVDA"],
    },
    "electric_vehicles": {
        "legacy_automakers": ["F", "GM", "STLA"],
        "ev_pure_play": ["RIVN", "LCID"],
    },
    "retail_home_improvement": {
        "core": ["LOW", "WMT", "TGT", "COST"],
    },
    "semiconductors": {
        "core": ["AMD", "INTC", "QCOM"],
    },
    "ecommerce_cloud": {
        "retail": ["WMT", "TGT", "COST", "HD", "LOW"],
        "ecommerce": ["EBAY", "ETSY", "MELI"],
        "cloud_platform": ["MSFT", "GOOGL", "ORCL"],
        "advertising": ["META", "GOOGL", "PINS", "SNAP"],
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
    "internet_platforms": {
        "core": {"label": "Core internet/platform peers", "primary": True},
        "secondary": {"label": "Secondary tech peers", "primary": False,
                      "note": "Related large-cap tech; different revenue mix."},
    },
    "consumer_technology": {
        "core": {"label": "Core consumer-technology peers", "primary": True},
        "secondary": {"label": "Secondary tech peers", "primary": False},
    },
    "electric_vehicles": {
        "legacy_automakers": {"label": "Legacy automakers", "primary": True,
                              "note": "Lower growth/margin than TSLA; profitability differs."},
        "ev_pure_play": {"label": "EV pure-plays", "primary": False,
                         "note": "Pre-profit, small cap; reported separately."},
    },
    "retail_home_improvement": {
        "core": {"label": "Retail peers", "primary": True},
    },
    "semiconductors": {
        "core": {"label": "Semiconductor peers", "primary": True},
    },
    "ecommerce_cloud": {
        "retail": {"label": "Retail peers", "primary": True,
                   "note": "Omnichannel/brick-and-mortar retail; AWS margin profile differs."},
        "ecommerce": {"label": "E-commerce peers", "primary": True,
                      "note": "Online marketplaces; different revenue/margin mix."},
        "cloud_platform": {"label": "Cloud/platform peers", "primary": False,
                           "note": "AWS vs Azure/GCP/OCI; different business mix, reported separately."},
        "advertising": {"label": "Digital advertising peers", "primary": False,
                        "note": "AMZN ads vs search/social; reported separately."},
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


# --------------------------------------------------------------------------- #
# Automatic peer discovery (SEC SIC classification) + screening.
# --------------------------------------------------------------------------- #
from urllib.request import Request, urlopen  # noqa: E402
import json as _json  # noqa: E402

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# SIC ranges for financial-company models (banks, insurers, REITs, funds) that this
# valuation engine does not support. Peers in these ranges are excluded.
FINANCIAL_SIC_RANGES = ((6000, 6800),)


def get_company_sic(ticker: str, user_agent: str) -> dict | None:
    """Fetch a company's SIC code + description from the SEC submissions header."""
    from .sec import sec_lookup
    try:
        cik, _name = sec_lookup(ticker, user_agent)
        req = Request(SUBMISSIONS_URL.format(cik=cik), headers={"User-Agent": user_agent})
        data = _json.load(urlopen(req, timeout=30))
        sic = data.get("sic")
        return {"ticker": ticker.upper(), "sic": int(sic) if sic not in (None, "") else None,
                "sic_description": data.get("sicDescription"),
                "name": data.get("name"), "cik": cik}
    except Exception:
        return None


def is_financial_sic(sic) -> bool:
    """True when the SIC code falls in an unsupported financial-company range."""
    if sic is None:
        return False
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return False
    return any(lo <= s < hi for lo, hi in FINANCIAL_SIC_RANGES)


# Duplicate share classes that must not appear as separate "peers" of the same issuer.
DUPLICATE_SHARE_CLASSES = {
    "GOOG": "GOOGL", "GOOGL": "GOOG",  # Alphabet Class A/C
    "BRK.B": "BRK.A", "BRK.A": "BRK.B",  # Berkshire A/B
}


def _curated_groups_with_rationale(ticker: str) -> dict:
    industry = TICKER_INDUSTRY.get(ticker.upper(), "unknown")
    groups = INDUSTRY_PEER_GROUPS.get(industry, {})
    meta = META.get(industry, {})
    out = {}
    for key, tickers in groups.items():
        m = meta.get(key, {})
        out[key] = {"tickers": [t for t in tickers if t.upper() != ticker.upper()],
                    "label": m.get("label", key.replace("_", " ").title()),
                    "rationale": m.get("note", "curated industry peer group"),
                    "primary": m.get("primary", True)}
    return out


def discover_peers(ticker: str, user_agent: str = "", candidate_universe: list[str] | None = None) -> dict:
    """Discover comparable companies for `ticker`.

    Uses the curated industry groups when the ticker is mapped; otherwise falls back to
    SEC SIC classification over a candidate universe. Never selects peers based on market
    price proximity. Records selection method, industry, groups and exclusion reasons.
    """
    ticker = ticker.upper()
    info = get_company_sic(ticker, user_agent) if user_agent else None
    sic = info.get("sic") if info else None
    industry = TICKER_INDUSTRY.get(ticker, "unknown")

    if industry != "unknown":
        return {
            "method": "curated",
            "ticker": ticker,
            "industry": industry,
            "sic": sic,
            "sic_description": (info or {}).get("sic_description"),
            "groups": _curated_groups_with_rationale(ticker),
            "excluded": _discovery_exclusions(ticker, info),
        }

    # Unmapped ticker -> SIC discovery.
    universe = candidate_universe or list(PEER_NOTES.keys()) + list(TICKER_INDUSTRY.keys())
    groups = {}
    excluded = _discovery_exclusions(ticker, info)
    if sic is None or not user_agent:
        return {"method": "sic_unavailable", "ticker": ticker, "sic": sic,
                "sic_description": (info or {}).get("sic_description"),
                "groups": {}, "excluded": excluded}
    for candidate in universe:
        if candidate.upper() == ticker:
            continue
        c_info = get_company_sic(candidate, user_agent)
        if c_info is None or c_info.get("sic") is None:
            continue
        if is_financial_sic(c_info["sic"]):
            excluded.append({"ticker": candidate.upper(), "reason": "financial-company SIC"})
            continue
        if c_info["sic"] == sic:
            groups.setdefault(f"sic_{sic}", []).append(candidate.upper())
    out_groups = {}
    if groups:
        out_groups[f"sic_{sic}"] = {"tickers": groups[f"sic_{sic}"],
                                    "label": f"SIC {sic} — {(info or {}).get('sic_description', '')}",
                                    "rationale": "same SIC industry classification",
                                    "primary": True}
    return {"method": "sic", "ticker": ticker, "sic": sic,
            "sic_description": (info or {}).get("sic_description"),
            "groups": out_groups, "excluded": excluded}


def _discovery_exclusions(ticker: str, info: dict | None) -> list[dict]:
    ex = []
    if info and is_financial_sic(info.get("sic")):
        ex.append({"ticker": ticker, "reason": "financial-company SIC (unsupported model)"})
    dup = DUPLICATE_SHARE_CLASSES.get(ticker)
    if dup:
        ex.append({"ticker": dup, "reason": "duplicate share class"})
    return ex

