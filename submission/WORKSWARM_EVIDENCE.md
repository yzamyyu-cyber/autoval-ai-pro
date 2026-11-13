# WorkSwarm Execution Evidence — AutoVal AI Pro

> Concise record of WorkSwarm's actual contribution to the AutoVal AI Pro final project.
> All commands, errors and results below are real terminal/tool output from the saved runs;
> nothing is invented. (Screenshots were not captured in this session — suggested capture
> points are listed at the end.)

## 1. Financial task & original input

- **Task:** from a single ticker, automatically retrieve SEC financial statements and market
  data, then produce and independently verify a multi-method equity valuation
  (driver-based DCF, company-specific WACC, investment bridge, P/E + EV/EBITDA).
- **Original input:** a stock ticker only (e.g. `MSFT`, then a fresh `HD`). No manual
  financial-statement or price entry.

## 2. Tools & Python commands used

```bash
cd <PROJECT_ROOT>                                       # the folder containing run_analysis.py
set -a && . ./.env && set +a                          # load SEC_USER_AGENT (never displayed)
.venv/bin/python run_analysis.py --mode live --ticker TICKER --output outputs/<case>
.venv/bin/python verify_output.py --analysis outputs/<case>/analysis.json
.venv/bin/python -m unittest discover -s tests -v      # 97 → 98 tests
.venv/bin/python -m streamlit run app.py               # dashboard
```

## 3. How WorkSwarm detected missing / inconsistent SEC XBRL fields

The engine's design is to **stop with an informative error** rather than fabricate a missing
figure. During the Home Depot fresh case, two such stops occurred:

**Attempt 1 — missing capital-expenditure tag**
```
ValueError: Insufficient matched annual SEC facts for reliable FCFF
(matched years=0; missing categories=['capital expenditure']).
```
Diagnosis: HD reports capex under `PaymentsToAcquireProductiveAssets`, not
`PaymentsToAcquirePropertyPlantAndEquipment`.

**Attempt 2 — stale debt tag**
```
ValueError: Noncurrent long-term debt not reported at cash reporting date 2026-08-02;
manual reconciliation required
```
Diagnosis: HD's `LongTermDebtNoncurrent`/`LongTermDebtCurrent` were last filed in 2011; HD
uses `LongTermDebtAndCapitalLeaseObligations` (+ current) and `CommercialPaper`.

## 4. The reusable corrections (not HD-hardcoded)

| File | Change |
|---|---|
| `autoval/sec.py` | `instant_at_date_multi()`; capex tag fallback `PaymentsToAcquirePropertyPlantAndEquipment` → `PaymentsToAcquireProductiveAssets`; debt tags `LongTermDebtNoncurrent` → `LongTermDebtAndCapitalLeaseObligations` → `LongTermDebt`, `LongTermDebtCurrent` → `LongTermDebtAndCapitalLeaseObligationsCurrent`, `ShortTermBorrowings` → `CommercialPaper` |
| `autoval/forecast_data.py` | capex tag fallback (same) |
| `autoval/pipeline.py` | summary bridge handles `None` restricted-investments |

These are **priority-order fallbacks** with stale-tag rejection and lease-inclusive
convention (finance leases already inside the debt tags are not added again).

## 5. Successful third execution (HD)

```
market_price: $351.31 (2026-11-11) · FY 2026-02-01
Bear $99.10 · Base $200.49 · Bull $336.88 · WACC 8.18%
Debt: noncurrent $43,951M + current $4,697M + commercial paper $4,248M = $52,896M
Net debt $50,811M (cash $2,085M)   ← reconciled to the Aug 2, 2026 10-Q
Relative valuation: unavailable (no HD peer group) — disclosed, not fabricated
```

## 6. Independent verification & automated tests

- `verify_output.py` → **`passed: true`** on every completed run (Decimal re-derivation of
  the DCF to <$0.01/share).
- Automated tests: **97/97** at HD completion → **98/98** after the dashboard `KeyError`
  fix (`tests/` covering finance, SEC, forecast, WACC, relative, market, technical).

## 7. Agent vs deterministic Python — division of responsibility

| Performed by the agent (WorkSwarm) | Performed by deterministic Python code |
|---|---|
| Read files, chose the workflow, interpreted errors, proposed the corrections, wrote documentation | All valuation math: SEC extraction, TTM/forecast, WACC, DCF, EV bridge, P/E & EV/EBITDA, verification |
| Diagnosed *why* HD failed (tag mismatch) | Raised the informative errors that exposed the mismatch |
| Wrote/updated SKILL.md, README, audits, evidence | Computed every number; the agent never computed valuation arithmetic |

## 8. Saved output paths

- `outputs/demo_run/` — synthetic self-check (verification passed).
- `outputs/workswarm_msft_v8/` — full MSFT pipeline + relative valuation + audits.
- `outputs/hd_fresh_skill/` — Home Depot fresh case + `RECORD.md`.
- `submission/FINAL_FINANCIAL_VERIFICATION.md` — Base-case DCF numerical walkthrough.

## 9. Suggested screenshot capture points (not fabricated here)

1. Terminal output of the **first HD failure** (`missing capital expenditure`).
2. Terminal output of the **second HD failure** (`Noncurrent long-term debt not reported`).
3. The **successful HD run** summary (bear/base/bull + debt reconciliation).
4. The **Streamlit "Relative valuation" / "Forecast" tab** showing the driver DCF.

> To attach genuine screenshots, re-run the commands above (or use the saved
> `outputs/hd_fresh_skill/RECORD.md`) and capture the actual terminal/UI output. No
> screenshot or measurement in this record is fabricated.
