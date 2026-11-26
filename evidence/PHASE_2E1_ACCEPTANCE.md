# Phase 2E.1 — Targeted Financial Recovery Acceptance

Checkpoint: `638aebb` · Branch: `ai-financial-reconciliation`

## MCD valuation anomaly (Task 1)

Two reusable root causes fixed (no hardcoded values, no "divide by 1M" shortcut):

1. **Share-unit inconsistency.** McDonald's tags weighted-average diluted shares in MILLIONS
   (`711.0`) while its point-in-time common shares are actual units (`705,784,744`).
   `analyze_driver_valuation` used `diluted_shares` (711.0) directly, inflating the per-share
   DCF ~1e6×. Fixed with a unit-consistency guard in `sec.py` (rescale weighted-average shares
   when ~1e6× smaller than common shares): diluted 711.0 → 711,000,000.
2. **Net-debt metric misclassification.** The MCD proposal's `financial_definition` is
   "debt **less cash**" (already net of cash), but `apply.py::_classify_metric` fell through to
   `total_debt`, subtracting cash a second time ($38.627B → $37.434B). Fixed to recognize
   "less cash / net of cash / after cash" as `net_debt`.

**Result:** MCD base DCF/share $74.07M → **$72.40**; corrected net debt $37.434B → **$38.627B**
(gross debt $39.82B − cash $1.193B). Regression tests added for both.

## ORCL recovery (Task 2)

ORCL reports long-term debt under `LongTermNotesAndLoans` (not `LongTermDebtNoncurrent`).
Added the standard us-gaap tags (`LongTermNotesAndLoans`, `ConvertibleLongTermNotesPayable`,
`LongTermNotesPayable`) to the long-debt fallback list. Extraction now resolves:
total debt **$134.522B** = LongTermNotesAndLoans $117.712B + NotesPayableCurrent $7.625B +
finance lease $9.185B (no double-count); net debt **$98.153B**. The valuation regenerates
(equity is negative → quality `unavailable`, a correct mechanical outcome, not a tuning).

## JNJ and recovered-company acceptance (Task 3)

- **JNJ cash-only net debt** ($27.741B) is the balance-sheet net debt; JNJ's disclosed "net
  debt position ~$27.4B" additionally nets marketable securities (~$17.2B cash+securities).
  These are **different definitions** and are reported as such, not as exact matches.
- **UPS** no-correction control re-verified with identical inputs: net debt unchanged
  ($19.241B), base DCF/share $42.79.
- **PG** corrected net debt $23.56B, base DCF/share $69.30.
- WACC provenance / 5-year / multi-stage DCF / quality / exports regenerated through the
  deterministic engine; illustrative market assumptions used (no genuine dated quote was
  cached for these tickers).

## Frozen checkpoint (Task 4)

`evidence/recovery_completion_matrix.json` (20 companies) distinguishes: fully supported,
illustrative, low-confidence, financial-extraction-only, and unavailable.

- Full suite: **310 passed, 32 subtests passed**.
- 91/91 historical snapshot checks: **PASS** (these use preserved snapshots; they are NOT
  claimed as verification of the newly extracted data — the corrected snapshots are verified
  by the deterministic engine + independent arithmetic).

## API usage

**0 new paid LLM calls.** All fixes are deterministic extraction/unit/metric corrections
using cached filings and existing validated records.

## Remaining blockers

- **CAT / XOM** — deferred specialized accounting (captive finance / predecessor-successor).
- **ORCL** — valuation is negative-equity (unavailable) because net debt exceeds EV; a
  financial-data result, not a defect to tune away.
