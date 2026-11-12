"""External WACC data retrieval with a metadata envelope for every input.

Every function returns a dict with the same envelope shape:
  {value, unit, source, retrieved_at, period, kind, confidence, limitation, available}
On failure `available` is False and `value` is None with a `reason`.

No silent substitution: a missing live input stays marked unavailable and the caller
(build_company_wacc) decides whether company-specific WACC can be produced.
"""
from __future__ import annotations
from datetime import datetime, timezone
import requests
import pandas as pd
from .wacc import beta_ols, compute_wacc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(value, unit, source, period=None, kind="observed", confidence="medium",
         limitation=None, retrieved_at=None):
    return {"value": value, "unit": unit, "source": source,
            "retrieved_at": retrieved_at or _now(), "period": period,
            "kind": kind, "confidence": confidence, "limitation": limitation,
            "available": True}


def _fail(reason, source=None):
    return {"value": None, "available": False, "reason": reason, "source": source}


# --------------------------------------------------------------------------- #
# Risk-free rate: FRED DGS10 (10-year Treasury constant maturity), % -> decimal.
# --------------------------------------------------------------------------- #
def fetch_risk_free_rate(timeout: int = 60) -> dict:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "AutoValStudentResearch/1.0"})
        r.raise_for_status()
        lines = [ln for ln in r.text.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            return _fail("FRED DGS10 returned no data rows", url)
        last_date, last_val = None, None
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) >= 2 and parts[1].strip() not in ("", "."):
                try:
                    last_date, last_val = parts[0], float(parts[1])
                except ValueError:
                    continue
        if last_val is None:
            return _fail("FRED DGS10 has no valid observations", url)
        return _env(last_val / 100.0, "decimal (per annum)",
                    "FRED DGS10 — Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity",
                    period=last_date, confidence="high",
                    limitation="10-year par yield used as the risk-free proxy; not horizon-matched to the 5-year forecast.")
    except Exception as exc:
        # Fallback: Yahoo ^TNX (CBOE 10-Year Treasury Yield Index).
        try:
            import yfinance as yf
            df = yf.Ticker("^TNX").history(period="5d", interval="1d", actions=False)
            if df is not None and not df.empty and "Close" in df:
                yield_decimal = _tnx_to_decimal(df["Close"].iloc[-1])
                return _env(yield_decimal, "decimal (per annum)",
                            "Yahoo ^TNX (CBOE 10-Year Treasury yield) — fallback",
                            period=str(df.index[-1].date()), confidence="medium",
                            limitation="^TNX is quoted as a percent yield (e.g. 4.998 = 4.998%); divided by 100. Fallback because FRED DGS10 was unavailable.")
        except Exception:
            pass
        return _fail(f"FRED DGS10 and ^TNX fallback unavailable: {exc}", url)


def _tnx_to_decimal(tnx_value: float) -> float:
    """Yahoo ^TNX is reported as a percent yield (4.998 == 4.998%); convert to decimal.

    Note: the CBOE TNX index is classically 10x the yield, but Yahoo's `^TNX` feed in
    this environment reports the yield directly in percent (verified against ^FVX and
    ^TYX forming a coherent 5/10/30-year curve). Divide by 100 accordingly.
    """
    return float(tnx_value) / 100.0


# --------------------------------------------------------------------------- #
# Equity risk premium: Damodaran implied ERP (best-effort).
# --------------------------------------------------------------------------- #
def fetch_erp(timeout: int = 30) -> dict:
    """Damodaran implied ERP: parse the mature-market (United States) equity risk
    premium from his country-risk-premium table (HTML, robust to openpyxl absence)."""
    url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "AutoValStudentResearch/1.0"})
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for tbl in soup.find_all("table"):
            header = None
            us_row = None
            for row in tbl.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
                if not cells:
                    continue
                if header is None and cells[0].strip().lower() == "country":
                    header = cells
                if cells and cells[0].strip() == "United States":
                    us_row = cells
                    break
            if header is None or us_row is None:
                continue
            idx = next((i for i, h in enumerate(header)
                        if "equity risk" in h.lower() and "premium" in h.lower()), None)
            if idx is None or idx >= len(us_row):
                continue
            val = us_row[idx].replace("%", "").strip()
            try:
                erp = float(val) / 100.0
            except ValueError:
                continue
            return _env(erp, "decimal (per annum)",
                        "Aswath Damodaran (NYU Stern) mature-market implied equity risk premium (United States row)",
                        period="latest Damodaran country-risk-premium update", confidence="medium",
                        limitation="Implied ERP for the mature (US) market; updated periodically; a forward-looking estimate, not a historical average.")
        return _fail("Could not parse the United States ERP row from Damodaran country risk premium page", url)
    except ImportError as exc:
        return _fail(f"BeautifulSoup required to parse Damodaran ERP ({exc})", url)
    except Exception as exc:
        return _fail(f"Damodaran implied ERP unavailable: {exc}", url)


# --------------------------------------------------------------------------- #
# Beta: weekly adjusted returns vs market proxy (SPY), 5-year primary + 2-year secondary.
# --------------------------------------------------------------------------- #
def _weekly_close(ticker: str, years: int):
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=f"{years}y", interval="1wk",
                                   auto_adjust=True, actions=False)
    return df["Close"] if "Close" in df else pd.Series(dtype=float)


def _regress(stock_series: pd.Series, market_series: pd.Series) -> dict:
    joined = pd.concat([stock_series, market_series], axis=1, join="inner").dropna()
    joined.columns = ["stock", "market"]
    rs = joined["stock"].pct_change()
    rm = joined["market"].pct_change()
    common = pd.concat([rs, rm], axis=1, join="inner").dropna()
    common.columns = ["stock", "market"]
    res = beta_ols(common["market"].tolist(), common["stock"].tolist())
    res["start_date"] = str(common.index[0].date())
    res["end_date"] = str(common.index[-1].date())
    return res


def fetch_beta(ticker: str, market: str = "SPY", years: int = 5, timeout: int = 30) -> dict:
    try:
        s5 = _weekly_close(ticker, years)
        m5 = _weekly_close(market, years)
        if s5.empty or m5.empty:
            return _fail(f"No weekly price history for {ticker} or {market}")
        primary = _regress(s5, m5)
        if primary["n"] < 60:
            return _fail(f"Too few weekly observations ({primary['n']}) for a stable beta")
        s2 = s5.iloc[-104:]  # ~2 years of the same series
        m2 = m5.iloc[-104:]
        secondary = _regress(s2, m2)
        divergence = None
        if secondary.get("n", 0) >= 30:
            diff = abs(primary["beta"] - secondary["beta"])
            if diff >= 0.25:
                divergence = f"5y beta {primary['beta']:.2f} vs 2y beta {secondary['beta']:.2f} differ by {diff:.2f}; both reported."
        return {
            "value": primary["beta"], "unit": "dimensionless",
            "source": f"yfinance weekly adjusted close regression of {ticker} on {market}",
            "retrieved_at": _now(), "period": f"{primary['start_date']}..{primary['end_date']}",
            "kind": "calculated", "confidence": "medium",
            "limitation": ("Weekly simple returns, OLS with intercept; low R-squared is common for single names. "
                           "Not adjusted for thin trading or corporate actions beyond the adjusted-close series."),
            "available": True,
            "r_squared": primary["r_squared"], "se_beta": primary["se_beta"], "n": primary["n"],
            "benchmark": market, "beta_2yr": secondary.get("beta"), "beta_2yr_n": secondary.get("n"),
            "divergence": divergence,
        }
    except Exception as exc:
        return _fail(f"Beta unavailable: {exc}")


# --------------------------------------------------------------------------- #
# Cost of debt & marginal tax (derived from SEC facts / documented assumption).
# --------------------------------------------------------------------------- #
def _latest_annual_interest(stock: dict):
    records = (stock.get("source") or {}).get("annual_records") or []
    if not records:
        return None
    return records[-1].get("interest", {}).get("value")


def build_company_wacc(ticker: str, stock: dict, user_agent: str = "") -> dict:
    """Assemble company-specific WACC from live inputs. Returns
    {"available", "wacc", "inputs", "calculation"} or {"available": False, "reason", "inputs"}.
    """
    inputs = {}
    inputs["risk_free_rate"] = fetch_risk_free_rate()
    inputs["equity_risk_premium"] = fetch_erp()
    inputs["beta"] = fetch_beta(ticker)

    price = stock.get("market_price")
    shares = stock.get("shares")  # point-in-time common shares (NOT weighted-average diluted)
    if price and shares and price > 0 and shares > 0:
        inputs["equity_value"] = _env(price * shares, "USD",
                                      "Latest market price × point-in-time common shares outstanding",
                                      period=stock.get("share_count_asof"), kind="calculated",
                                      confidence="medium",
                                      limitation="Share count is a point-in-time snapshot; price is a delayed close.")
    else:
        inputs["equity_value"] = _fail("Market price or point-in-time share count unavailable")

    debt = stock.get("total_debt")
    if debt is not None and debt > 0:
        inputs["debt_value"] = _env(debt, "USD", "SEC gross interest-bearing debt (book value proxy for market value)",
                                    period=stock.get("balance_sheet_asof"), kind="observed",
                                    confidence="medium", limitation="Book debt used as market-value proxy.")
    else:
        inputs["debt_value"] = _fail("Gross debt unavailable")

    interest = _latest_annual_interest(stock)
    if interest is not None and debt:
        pre_tax_cod = interest / debt
        inputs["pre_tax_cost_of_debt"] = _env(pre_tax_cod, "decimal (per annum)",
                                              "Annual interest expense ÷ gross debt (historical cost-of-debt proxy)",
                                              period=stock.get("financial_asof"), kind="calculated",
                                              confidence="low",
                                              limitation=("Historical proxy, NOT the current marginal borrowing rate; "
                                                          "does not average beginning/ending debt and may be distorted "
                                                          "by finance-lease interest or non-debt interest expense."))
    else:
        inputs["pre_tax_cost_of_debt"] = _fail("Interest expense or debt unavailable for cost-of-debt proxy")

    # Marginal tax: documented baseline assumption (NOT the effective historical rate).
    inputs["marginal_tax_rate"] = _env(0.21, "decimal", "US federal statutory marginal tax rate (assumed baseline)",
                                       kind="assumed", confidence="medium",
                                       limitation="21% US federal statutory baseline; excludes state/international adjustments. Sensitivity range 15%–27% recommended.")

    required = ["risk_free_rate", "equity_risk_premium", "beta", "equity_value",
                "debt_value", "pre_tax_cost_of_debt", "marginal_tax_rate"]
    missing = [k for k in required if not inputs[k].get("available")]
    if missing:
        return {"available": False, "reason": f"Missing WACC inputs: {', '.join(missing)}", "inputs": inputs}

    calc = compute_wacc(
        inputs["risk_free_rate"]["value"], inputs["beta"]["value"],
        inputs["equity_risk_premium"]["value"], inputs["equity_value"]["value"],
        inputs["debt_value"]["value"], inputs["pre_tax_cost_of_debt"]["value"],
        inputs["marginal_tax_rate"]["value"],
    )
    return {"available": True, "wacc": calc["wacc"], "inputs": inputs, "calculation": calc}
