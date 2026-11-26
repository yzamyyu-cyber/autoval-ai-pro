# AI Reconciliation — Phase 2B: Recovery, Regeneration and Generalization

Checkpoint: `6814879` · Branch: `ai-financial-reconciliation`

## 1. Approved-correction workflow (Task 1)

`autoval/reconciliation/apply.py` + `regenerate.py` + `approval.py` now form a complete,
dependency-aware correction pipeline:

- `apply_correction(extraction, proposal)` — deep-copies the extraction, overwrites only the
  disputed metric, and deterministically recomputes `total_debt` / `net_debt`.
- `regenerate_analysis(original_result, corrected_stock, ua)` — re-runs the whole downstream
  valuation on the corrected stock: **WACC** (capital weights + cost-of-debt proxy), the
  **five-year DCF**, **multi-stage DCF**, **reverse-DCF** inputs, **observed multiples**,
  **relative valuation**, **sensitivity**, **quality** and **provenance**. It reuses only the
  unchanged market-price history and financial-driver history.
- `apply_approved(proposal, extraction, snapshot_id, ua, original_result)` — binds approval to
  the exact **company, reporting period, snapshot identity and evidence**; rejects **outdated,
  duplicate, modified or unvalidated** proposals; a **no-correction** finding returns
  `no_change` and leaves the original analysis unchanged.

The original snapshot is never mutated; `regenerate_analysis` returns a new `result` dict with
`"reconciled": true`.

## 2. Completed case studies (Task 2)

### WMT (short-term borrowings correction)
- Validated proposal: add the omitted `ShortTermBorrowings` ($10.479B) to net debt.
- Impact (deterministic): net debt $35.235B → **$45.714B** (Δ +$10.479B), ≈ −$1.32/share.
- Regeneration re-runs WACC (higher debt weight) and the DCF (higher net debt in the equity
  bridge), independently reconciling the debt bridge.

### PG (current-debt + restricted-cash scope)
- Validated proposal: current-period total debt = `LongTermDebtNoncurrent` + `DebtCurrent`
  = $38.925B; stale `CommercialPaper` correctly excluded.
- Cash scope: combined `CashCashEquivalentsRestrictedCash…` tag flagged; the restricted-cash
  portion is disclosed as unresolved (the unrestricted-cash adjustment is not asserted without
  a separate restricted-cash fact).

### UPS (control)
- The agent produced "no correction warranted"; `apply_approved` returns `no_change`, leaving
  financial inputs and valuation outputs **unchanged**.

The original vs corrected analyses are shown side by side (records + regeneration unit test).

## 3. Generalization (Task 3)

| Ticker | Extraction | Agent outcome |
|---|---|---|
| MCD | debt blocked (stale nonzero short-term borrowings) | detected; **unresolved** — no current-period tag; agent did not fabricate a value |
| JNJ | debt blocked (stale nonzero current-portion debt) | detected; **unresolved** — no current-period tag; no fabrication |
| ORCL | failed (long-term debt tag not reported at cash date) | extraction failed → **unresolved** |
| CAT | specialized | recorded as **captive-finance** (debt/interest tags not standalone) — deferred |
| XOM | specialized | recorded as **predecessor-successor** identity resolution — deferred |

For MCD/JNJ/ORCL the agent correctly retained the unresolved status rather than inventing a
correction — the safety property the audit requires.

## 4. Safety and accuracy (Task 4)

Deterministic validation now checks **retrieved source facts**, not just the existence of a
citation: `source_fact_value` rejects a correct filing URL paired with an incorrect value by
comparing each cited component value against the companyfacts for that tag + period.

Regression tests (`tests/test_reconciliation.py`, 33 tests) cover: correct-URL/wrong-value,
wrong company, wrong reporting period, restricted cash treated as unrestricted, debt/lease
double-counting, malicious instructions in a formula, unsupported expressions in the restricted
arithmetic evaluator, approval against an outdated snapshot, duplicate application, correct
no-correction decisions, and missing LLM credentials.

The expression evaluator is a **restricted arithmetic evaluator** (digits, `+ - * / ( )`,
variable names only; no attribute access, no calls, no builtins). Arbitrary model-generated
code is never executed.

## 5. Contribution measurement (Task 5)

Machine-readable matrix: `evidence/reconciliation_evaluation_matrix.json`.

| Ticker | Extraction-only | AI-assisted |
|---|---|---|
| PG | debt blocked → valuation unavailable | validated correction → valuation available |
| WMT | net debt understated ($35.2B) | validated correction → $45.714B |
| UPS | correct | confirmed correct (no change) |
| MCD / JNJ / ORCL | blocked / failed | unresolved (no fabrication) |

Arithmetic accuracy (91/91 independent numerical checks) is reported **separately** from
source-data accuracy; passing arithmetic is not claimed to make the forecast economically
reasonable.

## 6. Verification (Task 6)

- Full automated suite: **291 passed, 32 subtests passed**.
- 91/91 numerical comparisons: **PASS, max_diff 0.000000**.
- AppTest: `tests/test_reconciliation_app.py` (2 tests) + `tests/test_reconciliation.py`
  (33 tests).
- Playwright: `evidence/reconciliation_interface.png` (0 page errors; detected issue + agent
  interface rendered).
- Records: `evidence/reconciliation_records/*.json` (PG, WMT, UPS, MCD, JNJ).
- Matrix: `evidence/reconciliation_evaluation_matrix.json`.

**Preserved:** checkpoint `6814879`, all prior commits and historical outputs. No SOTP / Monte
Carlo / unrelated features. No hardcoded company values; no market-price tuning. Not pushed or
merged.
