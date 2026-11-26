"""Centralized market-data validation policy (reusable by pipeline, UI and exports).

Classifies market-data provenance from actual inputs (source, observation date, retrieval
timestamp, ticker, currency) rather than trusting a bare label. Three legitimate modes:

  - current       fresh authorized market data (with observation + retrieval timestamps)
  - saved         a dated historical snapshot (explicitly historical analysis)
  - illustrative  hypothetical/assumed inputs (educational sensitivity only)
  - missing       no market data at all

Placeholder prices are rejected based on provenance, not numerical value. No consumer
silently switches to illustrative assumptions after a provider failure.
"""
from __future__ import annotations

import pandas as pd


def resolve_market(ticker: str, explicit_mode: str, fetch, saved_price=None, saved_price_date=None):
    """Resolve live market data into (market_source, market_mode, closes, price, price_date).

    The default is a genuine provider fetch. A provider failure yields mode='missing'
    (never an auto-substituted 'illustrative'). An explicit 'saved' selection loads a
    genuine dated historical snapshot (price + observation date). An explicit
    'illustrative' selection stores the hypothetical price SEPARATELY and never as a
    genuine market_price.
    """
    explicit_mode = (explicit_mode or "").strip()
    if explicit_mode == "saved":
        price = float(saved_price) if saved_price is not None else None
        pdate = saved_price_date
        if price is not None and pdate and price > 0:
            source = {"mode": "saved", "provider": "saved snapshot (genuine dated observation)",
                      "price_date": pdate, "classification": "dated saved data"}
            return source, "saved", pd.Series(dtype=float), price, pdate
        # "saved" selected but no genuine dated snapshot supplied -> missing (never fabricated)
        source = {"mode": "missing", "provider": "saved snapshot unavailable",
                  "classification": "missing market data"}
        return source, "missing", pd.Series(dtype=float), None, None
    if explicit_mode == "illustrative":
        source = {"mode": "illustrative", "provider": "explicit illustrative assumptions",
                  "classification": "illustrative assumptions"}
        return source, "illustrative", pd.Series(dtype=float), None, None
    try:
        market = fetch(ticker)
        return (market["market_source"], "current", market["close_prices"],
                market["market_price"], market["price_date"])
    except Exception as exc:  # noqa: BLE001 - provider failures are expected and must not crash
        source = {"mode": "missing", "provider": "none (provider failure)",
                  "classification": "missing market data", "reason": str(exc)[:200]}
        return source, "missing", pd.Series(dtype=float), None, None


def classify_market_data(market_source: dict | None, price) -> str:
    """Return 'current' | 'saved' | 'illustrative' | 'missing' from actual provenance."""
    if market_source is None or not isinstance(market_source, dict):
        return "missing"
    provider = market_source.get("provider")
    price_date = market_source.get("price_date")
    mode = market_source.get("mode")
    if mode == "current" and provider and price_date and price:
        return "current"
    if mode == "saved" and price_date:
        return "saved"
    if mode == "illustrative":
        return "illustrative"
    return "missing"


def is_genuine(mode: str) -> bool:
    """A genuine market observation (current or dated-saved), not illustrative/missing."""
    return mode in ("current", "saved")


def classify_wacc(wacc_block: dict | None, beta_available: bool, equity_available: bool) -> str:
    """Classify WACC as 'company-specific' | 'illustrative' | 'unavailable'."""
    if not wacc_block or not wacc_block.get("available"):
        return "unavailable"
    # company-specific only when the market-calibrated inputs (beta, equity value) are
    # genuine observations, not assumed placeholders.
    if beta_available and equity_available:
        return "company-specific"
    return "illustrative"
