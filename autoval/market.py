"""Prototype-only yfinance quote/history adapter; check usage rights before deployment."""
import pandas as pd


def fetch_market(ticker: str) -> dict:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Missing yfinance: run pip install -r requirements.txt") from exc
    try:
        df = yf.Ticker(ticker).history(period="5y", interval="1d", auto_adjust=False, actions=False)
    except Exception as exc:
        raise RuntimeError(f"Market provider error: {exc}") from exc
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
                              "license_warning": "Public redistribution or commercial website use may require a licensed data provider"}}
