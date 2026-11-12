# Execution Evidence Index

Concise, sanitized evidence for the AutoVal AI Pro final project. All values below are
real terminal/tool outputs; no screenshots or measurements are invented. See the referenced
files (all under this repo) for full detail.

## 1. Offline DEMO (synthetic self-check)

- Command: `run_analysis.py --mode demo --ticker DEMO --output outputs/demo_run`
- Result: Bear $93.40 · Base $139.85 · Bull $215.17 vs fictional $145.00.
- Verification: `outputs/demo_run/verification.json` → `passed: true` (Decimal, <$0.01/share).

## 2. MSFT live analysis & financial-data corrections

- Full pipeline: `outputs/workswarm_msft_v8/` (driver DCF, company WACC ~10.03%,
  investment bridge, P/E + EV/EBITDA peers).
- FCFF reconciliation audit: `outputs/workswarm_msft_v6/FCFF_FINAL_RECONCILIATION.md`
  (closed the cash-flow vs driver FCFF difference to −$5.4B, no residual).
- Relative-valuation audit: `outputs/workswarm_msft_v7/RELATIVE_FINAL_AUDIT.md` and the
  EV/EBITDA data-quality correction in `outputs/workswarm_msft_v8/DATA_AUDIT.md`
  (ORCL debt, CRM/ADBE D&A tags).

## 3. Home Depot fresh-case (Skill self-reproduction, new industry)

- Full record: `outputs/hd_fresh_skill/RECORD.md`.
- Result: HD price $351.31 (2026-11-11) · Bear $99.10 · Base $200.49 · Bull $336.88 ·
  WACC 8.18%. Debt reconciled to the 10-Q ($52,896M total; $50,811M net).
- Relative valuation correctly unavailable (no HD peer group) — disclosed, not fabricated.

### Failed → successful HD attempts (summary)

1. **Failed:** `missing capital expenditure` — HD uses `PaymentsToAcquireProductiveAssets`.
2. **Failed:** `Noncurrent long-term debt not reported … 2026-08-02` — HD's debt tags differ.
3. **Succeeded** after both reusable tag corrections; independently verified.

## 4. Independent verification & tests

- `verify_output.py` → `passed: true` for every completed run (Decimal recomputation).
- Automated tests: **97/97 passing** (`python -m unittest discover -s tests`).
