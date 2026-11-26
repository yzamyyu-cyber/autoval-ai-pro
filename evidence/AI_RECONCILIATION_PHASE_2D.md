# AI Reconciliation — Phase 2D: Custom Taxonomy and Financial Recovery

Checkpoint: `ec021cf` · Branch: `ai-financial-reconciliation` · New local commit: see git log

## 1. Custom-taxonomy validation (Task 1)

The validation system no longer requires a standard us-gaap tag or a Companyfacts match when
the original filing supplies sufficient evidence:

- `TAG_DEFINITIONS` now includes alternate borrowing tags: `LongTermNotesAndLoans`,
  `NotesPayableCurrent`, `NotesPayable`, `LoansPayable`, `LongTermNotesPayable`,
  `ConvertibleLongTermNotesPayable`.
- `xbrl_tag_exists` accepts a tag present in the **original filing's inline XBRL**
  (`filing_facts`) even when Companyfacts lacks it — Companyfacts and inline XBRL are treated
  as two channels of the **same disclosure**, not independent underlying facts.
- `validate()` accepts `filing_facts` and cross-checks each cited value against **both**
  Companyfacts **and** the filing's inline XBRL (full namespace+tag, entity context, reporting
  period, accession/URL, statement row, definition, units, scale, sign).
- For a **blocked extraction** (no balance-sheet date), the reporting-period check binds to a
  valid period and the prompt uses the filing's report date as the reference period.

## 2. Recovery of four companies (Task 2)

Benchmarks (kept in the evaluation harness only, never shown to the agent):

| Ticker | Extraction | Validation | Agent components (USD) | Benchmark |
|---|---|---|---|---|
| ORCL | failed | **validated** | LongTermNotesAndLoans $117.712B + NotesPayableCurrent $7.625B + FinanceLeaseLiability $9.185B = **$134.522B** | noncurrent 117,712 / current 7,625 / leases 9,185 ✅ |
| MCD | debt_blocked | **validated** | LongTermDebtNoncurrent $39.82B − Cash $1.193B = **$38.627B** | debt less cash 38,627 ✅ |
| PG | debt_blocked | **validated** | LongTermDebtNoncurrent $21.897B + DebtCurrent $17.028B − Cash $15.365B = **$23.56B** | debt less cash 23,560 ✅ |
| JNJ | debt_blocked | **unresolved** | — | current 8,852 / LT debt 35,799 (could not establish reliably) |

ORCL's recovery is the key demonstration: its noncurrent borrowings are tagged under
`LongTermNotesAndLoans` (not `LongTermDebtNoncurrent`), which the standard extraction misses.
The agent recovered the value from the original filing's inline XBRL. JNJ remains **unresolved**
(honest — evidence insufficient), per the standing rule.

## 3. Walmart valuation verification (Task 3)

The corrected net debt **$35.235B → $45.714B** is supported (short-term borrowings $10.479B +
current LT debt $3.470B + noncurrent $36.462B + finance leases $6.832B − cash $11.529B).

**Forecast audit (root cause of the negative DCF):** the five-year DCF's enterprise value is
only ~$3.37B because the forecast's **D&A driver** is extracted from
`FinanceLeaseRightOfUseAssetAmortization` (~$0.6–0.9B/yr) instead of total depreciation &
amortization (~$12–13B/yr for Walmart). This understates FCFF by ~$11–12B per year, collapsing
enterprise value and making equity value negative (net debt $35–45B ≫ EV $3.37B). Enterprise
value appears almost unchanged after the correction because the correction only changes net
debt (the equity-bridge subtraction), not the FCFF forecast. This D&A-driver defect is
**reported, not silently corrected** — correcting it would be tuning the forecast toward the
market price, which is out of scope.

## 4. End-to-end acceptance (Task 4)

- Full suite: **298 passed, 32 subtests passed**.
- 91/91 numerical comparisons: **PASS, max_diff 0.000000**.
- AppTest + Playwright (reconciliation interface, 0 page errors).
- Regression tests added: custom taxonomy tags (accepted via filing facts), unsupported custom
  tags (rejected), wrong statement contexts (period mismatch), fabricated values, restricted
  cash, overlapping debt, stale approvals.
- Records: `evidence/reconciliation_records/{ORCL,MCD,PG,JNJ,WMT,UPS}_*.json`.
- Matrix: `evidence/reconciliation_evaluation_matrix_2d.json`.

**Preserved:** checkpoint `ec021cf` and prior outputs. No new valuation models, no hardcoded
values, no market-price tuning, no push/merge.
