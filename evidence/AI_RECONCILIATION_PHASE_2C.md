# AI Reconciliation — Phase 2C: Original-Filing Intelligence and Financial Recovery

Checkpoint: `ec021cf` · Branch: `ai-financial-reconciliation`

## 1. Original-filing evidence retrieval (Task 1)

New module `autoval/reconciliation/filing.py` reads the **original 10-K/10-Q HTML** and
extracts, instead of relying only on aggregated Companyfacts:

- **Inline XBRL facts** (`ix:nonFraction` / `ix:nonNumeric`) with their exact `value`,
  `scale`, `sign`, `decimals`, `unit` and `contextRef`.
- **Reporting contexts** (`xbrli:context` → `instant` / `startDate` / `endDate`) and
  **units** (`xbrli:unit` → USD / shares).
- **Accounting-note excerpts** around debt/cash/lease keywords (short-term borrowings,
  commercial paper, restricted cash, finance/capital lease, current portion, long-term debt).
- **Statement table rows** (rendered HTML rows).

The agent (`agent.py`) now retrieves this evidence for every debt/cash/lease issue and
passes the inline facts + note excerpts into the LLM prompt, recording accession, filing
URL, statement/note reference, definition, reporting dates, units and scaling in the
proposal. A missing standard XBRL tag triggers this deeper investigation rather than
terminating the research.

## 2. Independent source validation (Task 2)

`source_fact_value` now cross-checks each cited component value against **two independent
sources**: the SEC companyfacts snapshot **and** the original filing's inline XBRL facts
(when supplied via `filing_facts`). It never compares the proposal against a value supplied
by the LLM. The check validates consolidated scope, definitions, reporting periods, units,
signs, scaling and overlapping components, and rejects unsupported proposals even when their
arithmetic is correct. The formula evaluator remains a restricted arithmetic evaluator (no
arbitrary code execution).

## 3. PG and ORCL recovery (Task 3)

### PG — recovered (validated)
- Original extraction: `debt_blocked` (stale nonzero `CommercialPaper`; combined cash tag).
- Original-filing inline XBRL (10-Q `pg-20260930.htm`, filed 2026-10-22, accession
  `0000080424-26-000256`): `LongTermDebtNoncurrent` **$21.897B** + `DebtCurrent` **$17.028B**,
  combined `CashCashEquivalentsRestrictedCash…` **$15.365B**; `ShortTermBorrowings` /
  `CommercialPaper` / `FinanceLease*` **not separately tagged**.
- Note excerpts confirm "CASH, CASH EQUIVALENTS AND RESTRICTED CASH, END OF PERIOD $15,365"
  and commercial-paper financing disclosure.
- Proposal: current total debt = $21.897B + $17.028B = **$38.925B**. Validation: **validated**.

### ORCL — unresolved (honest)
- Original extraction: `failed` (noncurrent debt not reported at the cash date).
- Original-filing inline XBRL (10-Q `orcl-20260831.htm`, accession `0001193125-26-389274`):
  `FinanceLeaseLiability` $9.185B and `CashAndCashEquivalents` $36.369B are present, but
  `LongTermDebtNoncurrent` / `LongTermDebt` / `NotesPayable`-style tags are **absent** under
  the standard us-gaap set — the borrowings use a company-specific taxonomy not in the
  standard tag list. The agent correctly retained **unresolved** rather than fabricating.

### MCD / JNJ — unresolved
- Both `debt_blocked` (stale nonzero components). The agent could not establish a reliable
  current-period value from the available evidence and retained **unresolved**.

## 4. Recovery from an incomplete analysis (Task 4)

`investigate` operates on a **blocked** extraction: it reconstructs a minimal extraction
shape, retrieves companyfacts + the filing evidence, and produces a proposal **without**
requiring a prior successful DCF. `apply_approved` + `regenerate_analysis` then regenerate
all downstream calculations (WACC, five-year/multi-stage DCF, reverse-DCF inputs,
comparables, sensitivity, quality, provenance) through the deterministic engine once a
correction is approved.

## 5. Walmart acceptance evidence (Task 5)

Correction: net debt **$35.235B → $45.714B** (Δ +$10.479B short-term borrowings).

- **Filing reference**: 10-Q filed 2026-08-28, period ended 2026-07-31, accession
  `0000104169-26-000154`.
- **Debt-component reconciliation** (all at 2026-07-31):
  `LongTermDebtNoncurrent` $36.462B + `LongTermDebtCurrent` $3.470B + `ShortTermBorrowings`
  $10.479B + finance leases $6.832B − `CashAndCashEquivalents` $11.529B = **$45.714B**.
- **Non-overlap**: `DebtLongtermAndShorttermCombinedAmount` = $39.932B equals
  `LongTermDebtNoncurrent` + `LongTermDebtCurrent` ($36.462B + $3.470B) and **excludes**
  `ShortTermBorrowings`; the $10.479B is a separate commercial-paper fact, so it does not
  overlap the long-term debt or the separately-added finance leases.
- **Five-year DCF before/after** (illustrative 10% WACC — WMT's negative interest expense
  makes the company cost-of-debt proxy invalid, so WACC falls back to illustrative):
  enterprise value $3.366B (unchanged), equity value **−$31.869B → −$42.348B**,
  intrinsic/share **−$3.97 → −$5.28**, terminal weight 69.8%, terminal growth 2.0%.
- **Negative-DCF explanation**: the driver-based FCFF forecast produces an enterprise value
  ($3.37B) far below net debt ($35–45B), so equity value is mechanically negative. This is a
  model limitation (thin FCFF + heavy reinvestment + low EV), **not** corrected by tuning
  assumptions toward the market price.

## 6. Execution and documentation (Task 6)

- Full automated suite: **296 passed, 32 subtests passed**.
- 91/91 numerical comparisons: **PASS, max_diff 0.000000**.
- AppTest (`test_reconciliation_app.py` + `test_reconciliation.py`, 36 tests) + Playwright
  (`evidence/reconciliation_interface.png`, 0 page errors).
- Regression tests added for: custom inline XBRL tags, wrong statement contexts (period
  mismatch), unsupported source values, overlapping debt, incomplete initial analyses, and
  correction regeneration.
- Records: `evidence/reconciliation_records/{PG,ORCL,MCD,JNJ,WMT,UPS}_*.json`.
- Matrix: `evidence/reconciliation_evaluation_matrix_2c.json`.

**Preserved:** checkpoint `ec021cf` and all prior outputs. No new valuation models, no
hardcoded values, no market-price tuning, no push/merge.
