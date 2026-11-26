# Cross-Industry Validation (additional 13 tickers)

Production `get_sec_financials` (SEC extraction) was executed for 13 previously untested
tickers. Result: **1 passed, 12 failed** — revealing reusable extraction defects that
prevent generalization beyond the original 7 validation cases.

| Ticker | Result | Root cause |
|---|---|---|
| DIS | PASS | — |
| WMT, NKE, XOM, CAT | FAIL | FCFF cross-check: `matched years=0` (CFO/capex/interest tag variants not matched) |
| COST, KO, PG, MCD, UPS, AMD | FAIL | stale nonzero short-term borrowings → debt reconciliation raises |
| JNJ | FAIL | stale nonzero current-portion long-term debt → raises |
| ORCL | FAIL | long-term debt tag not reported at cash date |

## Reusable defects identified (to fix before claiming generalization)

1. **FCFF cross-check is over-strict.** `get_sec_financials` requires CFO, capex and
   interest to share matched annual years via a narrow tag set. Companies using
   alternative capex/interest tags (WMT/NKE/XOM/CAT) fail with `matched years=0`.
2. **Debt reconciliation raises on stale nonzero components.** A stale (prior-period)
   short-term borrowing / current-portion figure causes a hard `ValueError` instead of a
   flagged, disclosed zero. This blocks COST/KO/PG/MCD/UPS/AMD/JNJ.

These are extraction robustness issues, not financial-model defects. The seven original
tickers pass because their tags happen to match the primary tag set.

## Status

- Original 7: validated (see prior evidence).
- Additional 13: 1 PASS, 12 blocked by the two reusable extraction defects above.
- Unsupported classes (banks/insurers/REITs/ETFs) and invalid tickers: not yet executed.
