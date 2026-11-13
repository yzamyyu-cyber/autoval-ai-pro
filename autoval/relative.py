"""Pure relative-valuation math (P/E and EV/EBITDA). No network I/O."""
from __future__ import annotations
from math import isfinite


def _percentile(values, p):
    """Nearest-rank percentile on sorted values (documented method)."""
    s = sorted(float(v) for v in values if v is not None)
    if not s:
        return None
    n = len(s)
    idx = int(round(p * (n - 1)))
    return s[idx]


def median(values):
    s = sorted(float(v) for v in values if v is not None)
    if not s:
        return None
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def p25(values):
    return _percentile(values, 0.25)


def p75(values):
    return _percentile(values, 0.75)


def _clean_positive(values):
    """Return the subset that is finite and strictly positive (multiple is meaningful)."""
    return [float(v) for v in values if v is not None and isfinite(float(v)) and float(v) > 0]


def trailing_pe(price: float, ttm_diluted_eps: float) -> float | None:
    """GAAP trailing P/E. Returns None when EPS is non-positive (not meaningful)."""
    if ttm_diluted_eps is None or float(ttm_diluted_eps) <= 0:
        return None
    return float(price) / float(ttm_diluted_eps)


def pe_summary(peer_multiples: list[float], target_ttm_eps: float) -> dict:
    """Median/P25/P75 of peer trailing P/E -> implied price range for the target."""
    cleaned = _clean_positive(peer_multiples)
    m = median(cleaned)
    q25 = p25(cleaned)
    q75 = p75(cleaned)
    eps = float(target_ttm_eps) if target_ttm_eps else None
    def implied(mult):
        return mult * eps if mult is not None and eps and eps > 0 else None
    return {
        "sample_size": len(cleaned),
        "median_pe": m,
        "p25_pe": q25,
        "p75_pe": q75,
        "implied_price_median": implied(m),
        "implied_price_p25": implied(q25),
        "implied_price_p75": implied(q75),
        "excluded_negative": len(peer_multiples) - len(cleaned),
    }


def ev_ebitda(market_cap: float, total_debt: float, finance_leases: float,
              preferred: float, minority: float, cash: float, ebitda: float) -> float | None:
    """Enterprise value / EBITDA. EV = mcap + debt + leases + preferred + minority - cash.
    Returns None when EBITDA is non-positive or EV is invalid."""
    if ebitda is None or float(ebitda) <= 0:
        return None
    if market_cap is None:
        return None  # cannot compute EV without a market cap; do not treat it as zero
    ev = (float(market_cap) + float(total_debt or 0) + float(finance_leases or 0)
          + float(preferred or 0) + float(minority or 0) - float(cash or 0))
    if ev <= 0:
        return None
    return ev / float(ebitda), ev


def ev_ebitda_summary(peer_multiples: list[float], target_ebitda: float,
                      target_net_debt: float, target_shares: float) -> dict:
    """Median/P25/P75 EV/EBITDA -> implied EV -> equity -> price per diluted share."""
    cleaned = _clean_positive(peer_multiples)
    m = median(cleaned)
    q25 = p25(cleaned)
    q75 = p75(cleaned)
    ebitda = float(target_ebitda) if target_ebitda and target_ebitda > 0 else None
    def implied_price(mult):
        if mult is None or not ebitda or not target_shares:
            return None
        implied_ev = mult * ebitda
        implied_equity = implied_ev - float(target_net_debt)
        return implied_equity / float(target_shares)
    return {
        "sample_size": len(cleaned),
        "median_ev_ebitda": m,
        "p25_ev_ebitda": q25,
        "p75_ev_ebitda": q75,
        "implied_ev_median": (m * ebitda) if (m is not None and ebitda) else None,
        "implied_equity_median": (m * ebitda - float(target_net_debt)) if (m is not None and ebitda) else None,
        "implied_price_median": implied_price(m),
        "implied_price_p25": implied_price(q25),
        "implied_price_p75": implied_price(q75),
        "excluded_nonpositive": len(peer_multiples) - len(cleaned),
    }


def summarize_relative_valuation(target: dict, peers: dict, peer_map: dict) -> dict:
    """Compute per-group P/E and EV/EBITDA statistics and implied target prices."""
    target_eps = target.get("ttm_eps")
    target_ebitda = target.get("ttm_ebitda")
    target_net_debt = ((target.get("gross_debt") or 0) + (target.get("finance_leases") or 0)
                       + (target.get("preferred") or 0) + (target.get("minority") or 0)
                       - (target.get("cash") or 0))
    target_shares = target.get("ttm_diluted_shares") or target.get("shares_outstanding")

    groups = {}
    for group_key, tickers in peer_map.items():
        group_peers = [peers[t] for t in tickers if t in peers]
        valued = [p for p in group_peers if p.get("valued")]
        pe_list = [p["pe"] for p in valued if p.get("pe") is not None and p["pe"] > 0]
        ev_list = [p["ev_ebitda"] for p in valued if p.get("ev_ebitda") is not None
                   and p["ev_ebitda"] > 0 and p.get("ev_verifiable", True)]
        groups[group_key] = {
            "label": group_key,
            "sample_size": len(valued),
            "pe": pe_summary(pe_list, target_eps),
            "ev_ebitda": ev_ebitda_summary(ev_list, target_ebitda, target_net_debt, target_shares),
            "peers": [{
                "ticker": p["ticker"], "pe": p.get("pe"), "ev_ebitda": p.get("ev_ebitda"),
                "ttm_eps": p.get("ttm_eps"), "ttm_ebitda": p.get("ttm_ebitda"),
                "market_cap": p.get("market_cap"), "price_date": p.get("price_date"),
                "gross_debt": p.get("gross_debt"), "cash": p.get("cash"),
                "reason": p.get("reason"),
            } for p in group_peers],
        }
    return groups