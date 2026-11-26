# Phase 1 Acceptance Matrix

| Area | Status | Evidence |
|---|---|---|
| TTM extraction (additive, fiscal-calendar, rolling-12m) | ✅ | 7-ticker verification in FINANCIAL_RECONCILIATION.md |
| MSFT $85.92 defect | ✅ root-caused + corrected | VALUATION_REFERENCE.md |
| Identical-input arithmetic verification | ✅ | verify_reference.py: MSFT/AMZN annual base Δ=0.000000 |
| Independent reference engine (full chain) | ✅ | evidence/reference_calc.py (standalone, no autoval) |
| Peer screening (P/E vs EV/EBITDA separation) | ✅ | relative.py + per-metric `n` |
| Market-provider reliability (retries/failure state) | ✅ | market.py |
| Full 7-company independent execution | ⚠️ MSFT/AMZN done; 5 pending | reference_comparison.csv |
| Full AppTest matrix (7 tickers × all tabs) | ❌ pending | unit tests only (205) |
| Browser automation (Playwright) | ❌ pending | manual procedure below |
| Valuation-date stub discounting | ⚠️ qualified | full-year discounting, labeled approximation |
| Stock-split/dilution adjustment | ⚠️ qualified | shares as-filed, labeled reconstructed |

## Numerical reconciliation counts
- Valuations executed (independent): **2** (MSFT, AMZN annual base).
- Passed (Δ ≤ $0.01): **2**. Failed: **0**. Unverified: 13 (bear/bull/TTM/multi-stage + 5 tickers).

## Manual browser acceptance procedure (visual validation pending)
1. `streamlit run app.py` (see REPRODUCIBILITY.md).
2. For each ticker (MSFT/AMZN/AAPL/HD/GOOGL/TSLA/NVDA + DEMO): load, switch Annual↔TTM, open all six tabs, move sliders, press reset, download MD/JSON/CSV, switch tickers.
3. Confirm: no "Mature ROIC" KeyError; "Fiscal year ended" shows the correct FY; negative equity shows "N/A — Negative modeled equity"; no unhandled tracebacks.
