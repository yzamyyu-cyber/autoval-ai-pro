"""Prototype-only yfinance quote/history adapter; check usage rights before deployment."""
import time
import pandas as pd


def fetch_market(ticker: str, retries: int = 3, backoff: float = 1.5) -> dict:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Missing yfinance: run pip install -r requirements.txt") from exc

    last_exc = None
    df = None
    for attempt in range(retries):
        try:
            df = yf.Ticker(ticker).history(period="5y", interval="1d",
                                           auto_adjust=False, actions=False)
            break  # got a response (empty or not)
        except Exception as exc:  # noqa: BLE001 - provider failures are retried then surfaced
            last_exc = exc
            time.sleep(backoff * (attempt + 1))
    else:
        raise RuntimeError(f"Market provider error after {retries} attempts: {last_exc}") from last_exc

    if df is None or df.empty or "Close" not in df:
        raise ValueError("Market provider returned no daily close prices; ticker or provider may be unsupported")
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise ValueError("No valid close prices")
    close = df["Close"].astype(float)
    adjusted = df["Adj Close"].astype(float) if "Adj Close" in df else close
    closes = pd.Series(adjusted.values, index=pd.DatetimeIndex(df.index).tz_localize(None), name="close")
    if len(closes) < 201:
        raise ValueError("Need 201 daily price observations for technical analysis")
    date_text = str(df.index[-1].date())
    return {"market_price": float(close.iloc[-1]), "price_date": date_text,
            "close_prices": closes,
            "market_source": {"provider": "Yahoo Finance via yfinance (prototype/personal research)",
                              "price_basis": "Unadjusted daily closing price",
                              "backtest_basis": "Adjusted daily close if available; otherwise unadjusted (warning)",
                              "price_date": date_text,
                              "realtime": False,
                              "mode": "current",
                              "classification": "current authorized market data",
                              "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "license_warning": "Public redistribution or commercial website use may require a licensed data provider"}}
