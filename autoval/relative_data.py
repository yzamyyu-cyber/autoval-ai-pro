"""Peer market + financial data retrieval (quarterly/TTM) for relative valuation.

Deterministic math lives in `relative.py`; this module only retrieves and normalizes
data. Every peer record carries its source date, currency and data-quality notes.
"""
from __future__ import annotations
from __future__ import annotations
from datetime import date
from .sec import (annual_values, quarterly_values, latest_instant, sec_lookup,
                  fetch_json, FACTS_URL)
from .relative import trailing_pe, ev_ebitda
from .ttm import trailing_twelve_months


def _latest_price(ticker: str) -> tuple:
    """Latest split-adjusted (not dividend-adjusted) close and its date."""
    import time
    import yfinance as yf
    for period in ("1mo", "3mo", "6mo"):
        try:
            df = yf.Ticker(ticker).history(period=period, interval="1d",
                                           auto_adjust=False, actions=False)
        except Exception:
            continue
        if df is not None and not df.empty and "Close" in df:
            closes = df["Close"].dropna()
            if not closes.empty and float(closes.iloc[-1]) > 0:
                return float(closes.iloc[-1]), str(closes.index[-1].date())
        time.sleep(0.5)
    return None, None


def _ttm_quarters(facts: dict, tags: tuple[str, ...], unit: str = "USD") -> tuple:
    """Latest four quarters' values (sum) and the quarter-end dates used."""
    q = quarterly_values(facts, tags, unit=unit)
    ends = sorted(q)[-4:]
    return sum(q[e]["value"] for e in ends), ends


def _latest_val(facts: dict, tags: tuple[str, ...], unit: str = "USD"):
    v = latest_instant(facts, "us-gaap", tags, unit)
    return v["value"] if v else None


_DA_TOTAL_TAGS = ("DepreciationAndAmortization", "DepreciationDepletionAndAmortization")
_DA_COMPONENT_TAGS = ("Depreciation", "AmortizationOfIntangibleAssets",
                      "FinanceLeaseRightOfUseAssetAmortization")


def _ttm_da(facts: dict) -> tuple:
    """TTM D&A with an overlap guard: prefer a single total-D&A tag; else sum distinct
    components. Uses the validated additive TTM method (never omits Q4)."""
    for tag in _DA_TOTAL_TAGS:
        r = trailing_twelve_months(facts, (tag,))
        if r and r["value"]:
            return r["value"], tag
    total = 0.0
    used = []
    for tag in _DA_COMPONENT_TAGS:
        r = trailing_twelve_months(facts, (tag,))
        if r and r["value"]:
            total += r["value"]
            used.append(tag)
    return (total if used else None), "+".join(used)


def _gross_debt(facts: dict):
    """Gross interest-bearing debt (notes/bonds), EXCLUDING finance leases.

    Finance leases are added separately by the caller (`ev_ebitda` takes a distinct
    `finance_leases` argument), so this must never include them — otherwise they would
    be double-counted. Prefers the combined debt total tag, else sums the notes/bonds
    component tags; none of these include finance-lease liabilities.
    """
    total = latest_instant(facts, "us-gaap", ("DebtLongtermAndShorttermCombinedAmount",))
    if total:
        return total["value"]
    lt = latest_instant(facts, "us-gaap", ("LongTermDebtNoncurrent", "LongTermNotesPayable",
                                            "ConvertibleLongTermNotesPayable", "LongTermDebt"))
    cur = latest_instant(facts, "us-gaap", ("LongTermDebtCurrent", "NotesPayableCurrent",
                                             "DebtCurrent", "ConvertibleNotesPayableCurrent",
                                             "ConvertibleDebtCurrent"))
    st = latest_instant(facts, "us-gaap", ("ShortTermBorrowings",))
    parts = [(lt["value"] if lt else 0), (cur["value"] if cur else 0), (st["value"] if st else 0)]
    return sum(parts) if any(parts) else None


def retrieve_peer(ticker: str, user_agent: str) -> dict:
    rec = {"ticker": ticker.upper(), "valued": False}
    try:
        cik, name = sec_lookup(ticker, user_agent)
        facts = fetch_json(FACTS_URL.format(cik=cik), user_agent)
    except Exception as exc:
        rec["reason"] = f"SEC fetch failed: {exc}"
        return rec

    rec["company"] = name
    rec["cik"] = cik

    # TTM income statement items (validated additive method: FY + YTD − prior YTD,
    # so Q4 is never omitted).
    ni_ttm = trailing_twelve_months(facts, ("NetIncomeLoss", "ProfitLoss"))
    oi_ttm = trailing_twelve_months(facts, ("OperatingIncomeLoss",))
    ttm_ni = ni_ttm["value"] if ni_ttm else None
    ttm_oi = oi_ttm["value"] if oi_ttm else None
    ttm_da, da_tag = _ttm_da(facts)
    ttm_ebitda = (ttm_oi + (ttm_da or 0.0)) if ttm_oi is not None else None
    _period = ni_ttm.get("ytd_end") or ni_ttm.get("fy_end") if ni_ttm else None
    rec["reporting_period"] = f"TTM ended {_period}" if _period else None
    rec["da_tag"] = da_tag

    # TTM diluted shares: duration-weighted average of the latest four quarters'
    # weighted-average diluted shares (falls back to annual when quarters are missing).
    dil_q = quarterly_values(facts, ("WeightedAverageNumberOfDilutedSharesOutstanding",), unit="shares")
    if len(dil_q) >= 4:
        dil_ends = sorted(dil_q)[-4:]
        weights = []
        for e in dil_ends:
            f = dil_q[e]
            try:
                days = (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days
            except (KeyError, ValueError):
                days = 91
            weights.append(max(days, 1))
        ttm_dil_shares = sum(dil_q[e]["value"] * w for e, w in zip(dil_ends, weights)) / sum(weights)
    else:
        dil_a = annual_values(facts, ("WeightedAverageNumberOfDilutedSharesOutstanding",), unit="shares")
        ttm_dil_shares = (dil_a[sorted(dil_a)[-1]]["value"] if dil_a else None)

    ttm_eps = (ttm_ni / ttm_dil_shares) if (ttm_ni is not None and ttm_dil_shares) else None
    rec["ttm_net_income"] = ttm_ni
    rec["ttm_eps"] = ttm_eps
    rec["ttm_eps_basis"] = ("reconstructed (TTM net income ÷ duration-weighted TTM diluted shares)"
                            if ttm_eps is not None
                            else "unavailable (missing TTM net income or diluted shares)")
    rec["ttm_diluted_shares"] = ttm_dil_shares
    rec["ttm_ebitda"] = ttm_ebitda

    # market price + shares
    price, price_date = _latest_price(ticker)
    shares = latest_instant(facts, "dei", ("EntityCommonStockSharesOutstanding",), "shares")
    shares = shares["value"] if shares else None
    rec["price"] = price
    rec["price_date"] = price_date
    rec["shares_outstanding"] = shares
    rec["market_cap"] = (price * shares) if (price and shares) else None

    # EV components
    cash = _latest_val(facts, ("CashAndCashEquivalentsAtCarryingValue",))
    gross_debt = _gross_debt(facts)
    fin_lease = _latest_val(facts, ("FinanceLeaseLiability",))
    preferred = _latest_val(facts, ("PreferredStockValue",))
    minority = _latest_val(facts, ("MinorityInterest",))

    rec["gross_debt"] = gross_debt
    rec["finance_leases"] = fin_lease
    rec["preferred"] = preferred
    rec["minority"] = minority
    rec["cash"] = cash

    # P/E and EV/EBITDA
    rec["pe"] = trailing_pe(price, ttm_eps) if price and ttm_eps else None
    evr = ev_ebitda(rec["market_cap"], gross_debt, fin_lease, preferred, minority, cash, ttm_ebitda)
    if evr is not None:
        rec["ev_ebitda"], rec["ev"] = evr
    else:
        rec["ev_ebitda"], rec["ev"] = None, None

    rec["valued"] = bool(price and shares and ttm_eps and ttm_eps > 0 and ttm_ebitda and ttm_ebitda > 0)
    # EV/EBITDA is verifiable only when gross debt is tagged (missing debt != zero debt)
    # and EBITDA is positive and market cap is present.
    rec["ev_verifiable"] = bool(gross_debt is not None and ttm_ebitda and ttm_ebitda > 0
                                and rec.get("market_cap"))
    rec["reason"] = rec.get("reason", "") or ("ok" if rec["valued"] else "incomplete data")
    return rec


def build_relative_valuation(target_ticker: str, user_agent: str,
                             peer_map: dict, target_price: float = None,
                             target_price_date: str = None,
                             target_market_mode: str = "current") -> dict:
    """Retrieve peers and compute group statistics (P/E and EV/EBITDA)."""
    import time
    tickers = sum((list(g) for g in peer_map.values()), [])
    peers = {}
    for t in tickers:
        peers[t] = retrieve_peer(t, user_agent)
        time.sleep(0.5)  # reduce provider rate-limiting
    target = retrieve_peer(target_ticker, user_agent)
    if target_market_mode not in ("current", "saved"):
        # No genuine target market price: suppress the target's OWN market multiples so a
        # live/hypothetical price never masquerades as a genuine observation. Peer-implied
        # values below still use target fundamentals (TTM EPS/EBITDA), not the price.
        target["price"] = None
        target["price_date"] = None
        target["market_cap"] = None
        target["pe"] = None
        target["ev_ebitda"] = None
        target["ev"] = None
    elif target_price is not None:
        target["price"] = float(target_price)
        target["price_date"] = target_price_date or target.get("price_date")
        if target.get("shares_outstanding"):
            target["market_cap"] = float(target_price) * target["shares_outstanding"]
        target["pe"] = trailing_pe(target["price"], target.get("ttm_eps"))
        evr = ev_ebitda(target.get("market_cap"), target.get("gross_debt"),
                        target.get("finance_leases"), target.get("preferred"),
                        target.get("minority"), target.get("cash"), target.get("ttm_ebitda"))
        if evr is not None:
            target["ev_ebitda"], target["ev"] = evr
    return {"target": target, "peers": peers, "peer_map": peer_map}
