"""Moving averages and simple long/flat backtest with next-bar timing."""
import pandas as pd


def analyze_technical(closes: pd.Series, trading_cost_bps: float = 10) -> tuple[pd.DataFrame, dict]:
    if trading_cost_bps < 0 or trading_cost_bps > 1000:
        raise ValueError("Trading costs must be between 0 and 1000 basis points")
    if not isinstance(closes, pd.Series) or len(closes) < 201:
        raise ValueError("At least 201 daily closes are required for SMA 200 and a basic backtest")
    closes = closes.astype(float).copy().sort_index()
    if closes.index.has_duplicates or closes.isna().any() or (closes <= 0).any():
        raise ValueError("Close series must have unique timestamps and valid positive prices")
    df = pd.DataFrame({"close": closes})
    for window in (20, 50, 200):
        df[f"sma{window}"] = df["close"].rolling(window, min_periods=window).mean()
    df["signal"] = (df["sma20"] > df["sma50"]).astype(int)
    # Every signal is actionable only NEXT session: shift before multiplying returns.
    df["position"] = df["signal"].shift(1).fillna(0)
    df["daily_return"] = df["close"].pct_change().fillna(0)
    df["trade"] = df["position"].diff().fillna(df["position"]).abs()
    df["strategy_daily_return"] = df["position"] * df["daily_return"] - df["trade"] * trading_cost_bps/10000
    # Begin both strategies after SMA200 exists, equal comparison window.
    fair = df.loc[df["sma200"].notna()].copy()
    if len(fair) < 2:
        raise ValueError("Backtest window too short")
    fair.iloc[0, fair.columns.get_loc("strategy_daily_return")] = 0.0
    fair.iloc[0, fair.columns.get_loc("daily_return")] = 0.0
    fair["strategy_growth"] = (1 + fair["strategy_daily_return"]).cumprod()
    fair["buyhold_growth"] = (1 + fair["daily_return"]).cumprod()
    last = fair.iloc[-1]
    trend = "uptrend" if last["close"] > last["sma50"] > last["sma200"] else "not_confirmed"
    return df.join(fair[["strategy_growth", "buyhold_growth"]]), {
        "last_session": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        "sma20": float(df["sma20"].iloc[-1]), "sma50": float(df["sma50"].iloc[-1]),
        "sma200": float(df["sma200"].iloc[-1]), "trend": trend,
        "latest_signal": "long_next_bar" if df["signal"].iloc[-1] == 1 else "cash_next_bar",
        "comparison_start": str(fair.index[0].date()) if hasattr(fair.index[0], "date") else str(fair.index[0]),
        "strategy_total_return_pct": float((fair["strategy_growth"].iloc[-1]-1)*100),
        "buyhold_total_return_pct": float((fair["buyhold_growth"].iloc[-1]-1)*100),
        "cost_bps_per_trade": trading_cost_bps,
        "method": "SMA20 > SMA50, next-bar long/flat, 10 bps per position change; in-sample only",
        "warning": "Daily backtest ignores taxes, slippage, bid/ask spread and intraday fills; not a forecast",
    }
