# Holdout Evaluation — Phase 2F

Frozen version: commit `3723bbe` (+ share-unit + gross/net-debt guards committed before
evaluation). Five unseen companies: **PFE, INTC, DE, PEP, CSCO**.

## Baseline extraction (Method A, deterministic)

| Ticker | Extraction | Debt | Forecast history |
|---|---|---|---|
| PFE | ok | ok | **FAIL** (0 matched annual years) |
| INTC | debt blocked | stale ShortTermBorrowings | ok |
| DE | **raises** (no noncurrent LT debt tag) | — | — |
| PEP | debt blocked | stale noncurrent debt | ok |
| CSCO | debt blocked | stale ShortTermBorrowings | ok |

Baseline failures: **5/5** (4 debt, 1 forecast). Recovery rate is therefore measurable.

## AI agent (Method B raw LLM → Method C validated), 3 LLM calls

| Ticker | Raw LLM proposal | Validation | Correct? |
|---|---|---|---|
| INTC | total debt $50.134B = LongTermDebtNoncurrent + DebtCurrent | validated | ✅ correct |
| CSCO | short-term borrowings $8.424B = DebtCurrent − LongTermDebtCurrent | validated | ⚠️ partial (component, not full debt) |
| PEP | (none) | unresolved | ✅ correct no-fabrication |
| DE | (extraction raised → not investigated) | — | unrecovered |
| PFE | (no debt issue → not investigated) | — | forecast failure outside debt scope |

## Measured outcomes

- **Baseline extraction failures**: 5/5.
- **Recovered failures (validated + correct)**: 1/5 (INTC). Partial: 1 (CSCO).
- **Incorrect-correction acceptance rate**: 0 hard-incorrect; CSCO's proposal is a *component*
  (short-term borrowings) rather than complete debt — a scope limitation, not a fabrication.
- **Correct no-change / unresolved decisions**: PEP (correctly unresolved), PFE (no debt issue).
- **Unnecessary corrections**: 0.
- **Full valuation availability**: none at full confidence (all five have a debt or forecast
  gap); corrected snapshots are illustrative.
- **Source-data verification**: INTC/CSCO proposals use current-period inline-XBRL tags
  (LongTermDebtNoncurrent, DebtCurrent, LongTermDebtCurrent); no fabricated tags.
- **LLM calls / latency**: 3 calls (INTC 154s, PEP 302s, CSCO 111s); no token/cost metering
  exposed by the endpoint.

## Interpretation

The agent **recovered one of four debt failures correctly** (INTC), partially addressed a
second (CSCO, component-level), and **correctly declined to fabricate** PEP (noncurrent debt
genuinely stale). DE and PFE expose extraction gaps (alternative long-debt tags; revenue/capex
tag migration) that are **outside the debt reconciliation scope** and are documented for future
development. No company was replaced to manufacture a failure; recovery rate is
**1/5 correct + 1/5 partial**, reported honestly.

## Records

Sanitized proposals: `evidence/reconciliation_records/{INTC,CSCO,PEP,PFE}_*.json`.
Benchmarks: `evidence/holdout_benchmarks.json`. Results: `evidence/holdout_results.csv`.
