# AI Financial Reconciliation — Case-Study Evaluation

Three actual SEC case studies were executed with the **real LLM** (`deepseek-v4-pro-0813`) and
the **real SEC EDGAR API**. The expected benchmark values below were **not** provided to the
agent; they were derived separately (from the companyfacts) and used only for this evaluation.

## 1. PG — current-debt extraction + restricted vs unrestricted cash

**Detected issues (auto):** `debt_component_stale_nonzero` (CommercialPaper last reported
2026-06-30 = $4.837B, not at the 2026-09-30 cash date), `debt_unavailable`, and
`cash_restricted_scope` (cash uses the combined `CashCashEquivalentsRestrictedCash…` tag).

**Benchmark (for evaluation only):**
- Current-period total debt ≈ $38.925B = `LongTermDebtNoncurrent` $21.897B + `DebtCurrent` $17.028B.
- Current-period CommercialPaper is genuinely unresolved (no 2026-09-30 tag; the 2026-06-30
  $4.837B is stale and must not be silently carried forward).
- Combined cash $15.365B **includes restricted cash** and overstates unrestricted cash.

**Agent finding:** proposed total debt **$38.925B** (`LongTermDebtNoncurrent + DebtCurrent`),
correctly excluded the stale CommercialPaper, and explicitly flagged the commercial-paper and
restricted-cash uncertainties. **Validation: validated.** ✅ matches benchmark.

## 2. WMT — historical net-debt discrepancy ($45.7B vs $35.2B) and negative DCF

**Issue (manual):** historical net debt ≈ $45.7B vs current extraction ≈ $35.2B.

**Benchmark (for evaluation only):**
- `DebtLongtermAndShorttermCombinedAmount` = $39.932B equals `LongTermDebtNoncurrent` $36.462B +
  `LongTermDebtCurrent` $3.470B, and **excludes** short-term borrowings.
- `ShortTermBorrowings` = $10.479B (commercial paper) is a separate current-period fact that the
  extraction treated as zero.
- Finance leases $6.832B were correctly added; cash $11.529B was correctly subtracted.
- Correct net debt = $36.462B + $3.470B + $10.479B + $6.832B − $11.529B = **$45.714B**.
- The $10.479B omission understated net debt and total debt, contributing to the negative
  five-year DCF (equity value < net debt).

**Agent finding:** proposed net debt **$45.714B**, identified the omitted `ShortTermBorrowings`
($10.479B) as the cause, and confirmed finance-lease and cash treatment were correct.
**Validation: validated.** ✅ matches benchmark (the ~$45.7B historical figure).

## 3. UPS — control (existing reconciliation already correct)

**Issue (manual, control):** verify debt + finance-lease reconciliation; do not invent a
correction if already correct.

**Benchmark (for evaluation only):**
- Total debt $26.078B = `LongTermDebtAndCapitalLeaseObligations` $25.121B + `DebtCurrent` $0.957B.
- Finance lease $1.467B is **already included** in the lease-inclusive long-debt tag.
- Short-term borrowings = $0 (commercial-paper note disclosure).

**Agent finding:** "No correction warranted" — the agent recognized the existing calculation is
correct and did not invent a correction. The validator's `debt_lease_double_count` rule was
refined during this run so that a finance-lease component *listed but not added* is not a
false-positive double-count. ✅ control passes.

## Outcomes

| Case | Category | Validation | Outcome |
|---|---|---|---|
| PG | stale nonzero debt + restricted cash | validated | current-period debt reconstructed; stale component correctly excluded |
| UPS | control (finance lease + zero borrowings) | validated (no correction) | recognized correct, no invented correction |
| WMT | historical net-debt discrepancy | validated | short-term-borrowings omission identified ($10.479B) |

A rejected-proposal path and a failed-API path are covered deterministically in
`tests/test_reconciliation.py` (invalid citation, incompatible period, overlapping debt,
units/scaling, failed LLM/SEC).

## LLM execution (real, not fixture)

- Case-study run: 3 LLM investigations (PG, WMT, UPS) against live SEC companyfacts, each
  returning a structured JSON proposal.
- Debugging re-runs (formula-robustness fix, double-count rule refinement): 2 additional calls.
- Approximate total: 5 LLM chat-completions (≈ 5–10 minutes wall-clock; no per-token metering
  exposed by the endpoint). API keys were never written to source, screenshots or exports.
