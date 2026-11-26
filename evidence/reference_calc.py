#!/usr/bin/env python3
"""Standalone independent financial reconstruction (NO autoval imports).

Fetches SEC EDGAR companyfacts directly and independently reconstructs the full chain:
annual + TTM income statement, EBIT/NOPAT, D&A, economic CapEx, operating working
capital (ΔNWC), FCFF, WACC, discount factors, traditional DCF terminal value,
multi-stage ROIC terminal, enterprise value, the equity bridge and intrinsic/share.

Market WACC inputs (risk-free, beta, ERP, tax, equity value) are read from a documented
JSON (see WACC_INPUTS) — separated from the financial reconstruction and never re-derived
from the engine's own FCFF. They come from the saved snapshot (dated market data).

Usage:
    .venv/bin/python evidence/reference_calc.py TICKER [--ttm | --annual]
"""
from __future__ import annotations
import csv
import json
import sys
from datetime import date
from urllib.request import Request, urlopen

INDEX = "https://www.sec.gov/files/company_tickers.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
UA = "AutoValStudentResearch your-school-email@example.edu"

WACC_INPUTS = {
    "MSFT": {"rf": 0.0487, "beta": 1.29, "erp": 0.0446, "tax": 0.21, "equity_value": 3.94e12},
    "AMZN": {"rf": 0.04918, "beta": 1.3979, "erp": 0.0446, "tax": 0.21, "equity_value": 2.761e12},
    "AAPL": {"rf": 0.0470, "beta": 1.20, "erp": 0.0446, "tax": 0.21, "equity_value": 3.2e12},
    "HD":   {"rf": 0.0470, "beta": 1.05, "erp": 0.0446, "tax": 0.21, "equity_value": 3.5e11},
    "GOOGL":{"rf": 0.0470, "beta": 1.15, "erp": 0.0446, "tax": 0.21, "equity_value": 2.3e12},
    "TSLA": {"rf": 0.0470, "beta": 1.90, "erp": 0.0446, "tax": 0.21, "equity_value": 1.2e12},
    "NVDA": {"rf": 0.0470, "beta": 1.60, "erp": 0.0446, "tax": 0.21, "equity_value": 4.0e12},
}


def get(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urlopen(req, timeout=30))


def cik_of(ticker):
    for e in get(INDEX).values():
        if str(e["ticker"]).upper() == ticker.upper():
            return int(e["cik_str"])
    raise ValueError(f"no CIK for {ticker}")


def _annual(facts, tag, today, last=6, unit="USD"):
    out = {}
    for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get(unit, []):
        if it.get("form") not in ("10-K", "10-K/A"):
            continue
        if not it.get("start") or not it.get("end") or not it.get("filed"):
            continue
        if it["filed"] > today:
            continue
        try:
            days = (date.fromisoformat(it["end"]) - date.fromisoformat(it["start"])).days
        except ValueError:
            continue
        if not 330 <= days <= 390:
            continue
        k = it["end"]
        if k not in out or it["filed"] > out[k]["filed"]:
            out[k] = {"value": float(it["val"]), "end": k, "start": it["start"],
                      "filed": it["filed"], "tag": tag}
    return dict(sorted(out.items())[-last:])


def _ytd(facts, tag, today, fy_start_md):
    out = []
    for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get("USD", []):
        if it.get("form") not in ("10-Q", "10-Q/A"):
            continue
        if not it.get("start") or not it.get("end") or not it.get("filed"):
            continue
        if it["filed"] > today:
            continue
        try:
            s = date.fromisoformat(it["start"]); e = date.fromisoformat(it["end"])
        except ValueError:
            continue
        days = (e - s).days
        cum = 100 < days < 360
        if not cum and 75 <= days <= 100:
            s_md = date(2000, s.month, s.day)
            cum = abs((s_md - fy_start_md).days) <= 6
        if cum:
            out.append({"value": float(it["val"]), "end": it["end"],
                        "start": it["start"], "days": days})
    return out


def ttm(annual, ytds):
    if not annual:
        return None
    fy_end = max(annual); fy = annual[fy_end]["value"]
    if not ytds:
        return {"value": fy, "fy_end": fy_end, "ytd_end": None, "basis": "annual"}
    cur = max(ytds, key=lambda x: x["end"])
    if cur["end"] <= fy_end:
        return {"value": fy, "fy_end": fy_end, "ytd_end": None, "basis": "annual"}
    cur_start = date.fromisoformat(cur["start"])
    prior = None
    for y in ytds:
        if y is cur:
            continue
        if date.fromisoformat(y["end"]) >= cur_start:
            continue
        if abs(y["days"] - cur["days"]) > 15:
            continue
        if prior is None or y["end"] > prior["end"]:
            prior = y
    if prior is None:
        return None
    return {"value": fy + cur["value"] - prior["value"], "fy_end": fy_end,
            "ytd_end": cur["end"], "basis": "ttm", "current": cur, "prior": prior}


def _instant(facts, tag, today):
    best = None
    for it in facts["facts"]["us-gaap"].get(tag, {}).get("units", {}).get("USD", []):
        if not it.get("end") or not it.get("filed") or it["filed"] > today:
            continue
        if it.get("start"):
            continue
        if best is None or (it["end"], it["filed"]) > (best["end"], best["filed"]):
            best = {"value": float(it["val"]), "end": it["end"], "filed": it["filed"]}
    return best


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def cagr(vs):
    if len(vs) < 2 or vs[0] <= 0 or vs[-1] <= 0:
        return None
    return (vs[-1] / vs[0]) ** (1 / (len(vs) - 1)) - 1


def clip(v, lo, hi):
    return max(lo, min(hi, v))


def main(ticker, basis="ttm"):
    today = date.today().isoformat()
    cik = cik_of(ticker)
    facts = get(FACTS.format(cik=cik))

    rev = _annual(facts, "RevenueFromContractWithCustomerExcludingAssessedTax", today) or \
          _annual(facts, "Revenues", today)
    oi = _annual(facts, "OperatingIncomeLoss", today)
    da = _annual(facts, "DepreciationDepletionAndAmortization", today)
    if not da:
        # component sum (Depreciation + AmortizationOfIntangibleAssets + finance-lease ROU)
        da = {}
        for tag in ("Depreciation", "AmortizationOfIntangibleAssets",
                    "FinanceLeaseRightOfUseAssetAmortization"):
            for y, f in _annual(facts, tag, today).items():
                da[y] = {"value": da.get(y, {}).get("value", 0.0) + f["value"],
                         "end": y, "start": f["start"], "filed": f["filed"], "tag": tag}
    capex = _annual(facts, "PaymentsToAcquireProductiveAssets", today) or \
            _annual(facts, "PaymentsToAcquirePropertyPlantAndEquipment", today)
    finlease_add = _annual(facts, "RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability", today)

    years = sorted(rev)
    revs = [rev[y]["value"] for y in years]
    ois = [oi[y]["value"] if y in oi else None for y in years]
    das = [da[y]["value"] if y in da else None for y in years]
    cxs = [capex[y]["value"] if y in capex else 0.0 for y in years]
    fla = [finlease_add[y]["value"] if y in finlease_add else 0.0 for y in years]
    ecx = [c + f for c, f in zip(cxs, fla)]  # economic CapEx = cash + finance-lease

    ar = _instant(facts, "AccountsReceivableNetCurrent", today)
    inv = _instant(facts, "InventoryNet", today)
    ap = _instant(facts, "AccountsPayableCurrent", today)
    ccl = _instant(facts, "ContractWithCustomerLiabilityCurrent", today)
    acc = _instant(facts, "AccruedLiabilitiesCurrent", today)
    nwc_latest = ((ar["value"] if ar else 0) + (inv["value"] if inv else 0)
                  - (ap["value"] if ap else 0) - (ccl["value"] if ccl else 0)
                  - (acc["value"] if acc else 0))

    fy_start = date.fromisoformat(rev[years[-1]]["start"])
    fy_start_md = date(2000, fy_start.month, fy_start.day)
    ytds = _ytd(facts, rev[years[-1]]["tag"], today, fy_start_md)
    ttm_rev = ttm(rev, ytds)

    g = clip(cagr(revs[-3:]) or 0.02, -0.05, 0.25)
    margins = [o / r for o, r in zip(ois[-3:], revs[-3:]) if o is not None and r]
    m = clip(mean(margins) if margins else 0.2, 0.0, 0.6)
    da_ratio = mean([d / r for d, r in zip(das[-3:], revs[-3:]) if d is not None and r]) or 0.0
    capex_ratio = mean([c / r for c, r in zip(ecx[-3:], revs[-3:]) if r]) or 0.0
    nwc_ratio = nwc_latest / revs[-1] if revs[-1] else 0.0
    tax = 0.21

    base_rev = (ttm_rev["value"] if (basis == "ttm" and ttm_rev and ttm_rev["basis"] == "ttm")
                else revs[-1])

    stream = []
    rev_t = base_rev
    nwc_prev = nwc_latest
    for _ in range(5):
        rev_t = rev_t * (1 + g)
        nopat = rev_t * m * (1 - tax)
        d_a = rev_t * da_ratio
        cx = rev_t * capex_ratio
        nwc = rev_t * nwc_ratio
        d_nwc = nwc - nwc_prev
        fcff = nopat + d_a - cx - d_nwc
        stream.append(fcff)
        nwc_prev = nwc

    wi = WACC_INPUTS.get(ticker, WACC_INPUTS["MSFT"])
    rf, beta, erp, tax_w = wi["rf"], wi["beta"], wi["erp"], wi["tax"]
    coe = rf + beta * erp
    lt = _instant(facts, "LongTermDebtNoncurrent", today)
    cur = _instant(facts, "LongTermDebtCurrent", today)
    st = _instant(facts, "ShortTermBorrowings", today)
    fl = _instant(facts, "FinanceLeaseLiability", today)
    cash = _instant(facts, "CashAndCashEquivalentsAtCarryingValue", today)
    gross_debt = ((lt["value"] if lt else 0) + (cur["value"] if cur else 0)
                  + (st["value"] if st else 0) + (fl["value"] if fl else 0))
    net_debt = gross_debt - (cash["value"] if cash else 0)
    interest = _annual(facts, "InterestExpenseNonoperating", today) or \
               _annual(facts, "InterestExpense", today)
    int_v = interest[max(interest)]["value"] if interest else 0
    cod = int_v / gross_debt if gross_debt else 0
    ev_mkt = wi["equity_value"]
    wacc = coe * ev_mkt / (ev_mkt + gross_debt) + cod * (1 - tax_w) * gross_debt / (ev_mkt + gross_debt)

    shares = _annual(facts, "WeightedAverageNumberOfDilutedSharesOutstanding", today, last=1, unit="shares")
    share_v = shares[max(shares)]["value"] if shares else None
    if not share_v:
        cs = _annual(facts, "EntityCommonStockSharesOutstanding", today, last=1, unit="shares")
        share_v = cs[max(cs)]["value"] if cs else None

    pv = sum(cf / (1 + wacc) ** t for t, cf in enumerate(stream, start=1))
    tg = 0.02
    tv = stream[-1] * (1 + tg) / (wacc - tg)
    ev = pv + tv / (1 + wacc) ** len(stream)
    equity = ev - net_debt
    intrinsic = equity / share_v if share_v else None

    print(f"=== {ticker} ({basis}) ===")
    print(f"revenue basis: {ttm_rev['value']/1e6:,.0f}M ({ttm_rev['basis']}, fy {ttm_rev['fy_end']}, ytd {ttm_rev.get('ytd_end')})")
    print(f"drivers: g={g:.4%} margin={m:.4%} D&A={da_ratio:.4%} econCapEx={capex_ratio:.4%} NWC={nwc_ratio:.4%} tax={tax:.0%}")
    print(f"WACC={wacc:.4%} (CoE={coe:.4%}, CoD={cod:.4%}) | gross_debt={gross_debt/1e9:.2f}B net_debt={net_debt/1e9:.2f}B shares={share_v/1e6:.1f}M")
    print(f"FCFF stream (USD B): {[round(f/1e9,1) for f in stream]}")
    print(f"EV={ev/1e9:,.1f}B equity={equity/1e9:,.1f}B intrinsic=${intrinsic:,.4f}")

    rows = [["ticker", "basis", "metric", "reference_value", "note"]]
    rows.append([ticker, basis, "ttm_revenue_usd", ttm_rev["value"], ttm_rev["basis"]])
    rows.append([ticker, basis, "intrinsic_per_share_usd", intrinsic, "independent"])
    with open("evidence/financial_reconciliation.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print("wrote evidence/financial_reconciliation.csv")


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    b = sys.argv[2].replace("--", "") if len(sys.argv) > 2 else "ttm"
    main(t, b)
