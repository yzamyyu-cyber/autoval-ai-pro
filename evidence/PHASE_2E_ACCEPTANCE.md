# Phase 2E — Financial Recovery Completion

Checkpoint: `7630ba6` · Branch: `ai-financial-reconciliation`

## API usage (this phase)

**0 paid LLM calls.** The phase reused validated reconciliation records, cached SEC filings and
deterministic Python functions. No redundant investigation was performed.

## Task 1 — Targeted D&A acceptance (deterministic)

- Nike TTM D&A = **$750M** (tag `DepreciationDepletionAndAmortization`, period ended
  2026-08-31, consolidated) — matches the benchmark exactly.
- Alphabet depreciation (`Depreciation`), intangible amortization
  (`AmortizationOfIntangibleAssets`) and finance-lease ROU amortization
  (`FinanceLeaseRightOfUseAssetAmortization`) are distinct, non-overlapping tags.
- Quarterly amortization reconstruction filters ~3-month 10-Q increments and sums by fiscal
  year (no double-counting of the YTD 9-month facts).

## Task 2 — Completed recoveries (reused records, no new LLM)

| Ticker | Correction | Corrected net debt | Base DCF/share | Quality |
|---|---|---:|---:|---|
| PG | net debt (LongTermDebtNoncurrent + DebtCurrent − combined cash) | $23.56B | $69.30 | low_confidence |
| MCD | net debt (LongTermDebtNoncurrent − cash) | $37.43B | $74.07M | low_confidence |
| UPS | no-correction (control) | $19.24B (unchanged) | $42.79 | low_confidence |

Debt, cash, finance leases, WACC, five-year DCF, multi-stage DCF, quality and exports are
regenerated through the deterministic engine (`apply_correction` → `build_analysis`).

## Task 3 — JNJ resolved deterministically (no LLM)

Deterministic extraction + the original 10-Q note resolved JNJ: the current portion of
long-term debt is **included in "Loans and notes payable"** (`ShortTermBorrowings`), not a
separate line. Net debt = **$27.74B**, matching the filing's disclosed "≈$27.4B net debt".

Reusable mechanism: `sec.DEBT_INCLUDED_IN_SHORT_TERM_EVIDENCE` (source-backed, date-scoped,
note + URL), parallel to the existing `DEBT_ZERO_EVIDENCE`. This prevents double-counting
without weakening any safeguard.

## Task 4 — Compact acceptance

Machine-readable matrix: `evidence/recovery_completion_matrix.json` (20 companies;
extraction availability, AI status, valuation availability, net debt).

- Full suite: **308 passed, 32 subtests passed**.
- 91/91 historical numerical comparisons: **PASS, max_diff 0.000000**.
- AppTest (reconciliation UI) + Playwright (`reconciliation_interface.png`): **0 page errors**.

## Remaining blockers

- **ORCL** — long-term debt tag still not reported at the cash date (validated proposal
  exists, but extraction remains blocked; a source-backed evidence entry would be required).
- **CAT / XOM** — deferred specialized accounting (captive finance / predecessor-successor),
  per scope.

## LLM / token usage

0 calls this phase. Prior phases' actual runs are recorded in
`evidence/reconciliation_records/*.json` (no per-token metering exposed by the endpoint).
