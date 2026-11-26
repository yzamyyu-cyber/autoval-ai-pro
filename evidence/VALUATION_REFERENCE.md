# Valuation Reference (MSFT corrected)

Corrected MSFT valuation, identical assumptions across bases:
WACC **9.8072%**, net debt **$86.17B** (incl. $71.0B finance leases), diluted shares **7,453M**.

| Basis | Bear | Base | Bull |
|---|---:|---:|---:|
| Annual (5-yr) | $76.78 | $163.81 | $260.56 |
| **TTM (5-yr)** | $80.84 | **$171.70** | $272.71 |
| TTM multi-stage | $235.49 | **$332.37** | $446.43 |

## Identical-input verification (independent engine)

`evidence/verify_reference.py` + `evidence/batch_verify.py` read exact full-precision
snapshot inputs and independently recompute FCFF (per-case drivers), WACC (market inputs),
discount, terminal, multi-stage ROIC terminal and the bridge — without importing `autoval`.

**Batch result: 7 tickers × {annual, TTM} × {5yr, multistage} × {bear, base, bull} +
WACC = 91 combinations → 91 PASS, 0 FAIL, 0 UNAVAILABLE, max |Δ| = 0.000000.**

The earlier $163.24 vs $171.70 gap was **entirely** the approximate hardcoded WACC
inputs in the first reference draft — NOT a financial-reconstruction error. With identical
full-precision inputs, FCFF, WACC, 5-year DCF, multi-stage DCF and intrinsic all agree
exactly (Δ = 0, far tighter than the $0.01 criterion).

## The $85.92 defect — numerical bridge (unchanged)

See `FINANCIAL_RECONCILIATION.md`. TTM revenue collapsed to $182,286M (wrong
prior-comparable quarter) instead of $346,445M, scaling the base DCF to $85.92 instead of
$171.70.

## Independent reference calculation

`evidence/reference_calc.py` (standalone, no `autoval`) reconstructs the full chain from
SEC EDGAR; `evidence/verify_reference.py` does the identical-input arithmetic check.
