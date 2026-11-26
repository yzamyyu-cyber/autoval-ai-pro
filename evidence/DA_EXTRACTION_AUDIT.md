# D&A Extraction Audit — Phase 2D.1

Checkpoint: `2681a0b` · Branch: `ai-financial-reconciliation`

## 1. Architecture fix (Task 1)

New reusable module `autoval/da.py`:

- `resolve_annual_da(facts, years)` — **prefers the consolidated total-D&A tags**
  (`DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`,
  `DepreciationAmortizationAndAccretionNet`), merged across tag migrations by `annual_values`.
  Falls back to component reconstruction only when the total is unavailable **and** the core
  `Depreciation` component is present for every year. **Never substitutes finance-lease ROU
  amortization alone** for consolidated D&A.
- `resolve_ttm_da(facts)` — picks the consolidated total tag with the **most recent reporting
  period**, so a tag an issuer has migrated away from (e.g. Walmart's
  `DepreciationDepletionAndAmortization` after FY2019) is not reused.
- `forecast_data.py` now uses these resolvers for both annual `da` and `ttm.da`, and reports
  `da_status` (`consolidated` / `derived` / `unavailable`) + `da_detail` in the evidence centre.

Root cause fixed: Walmart's D&A was being taken from `FinanceLeaseRightOfUseAssetAmortization`
(~$0.9B/yr) because the old code summed available component tags and only consulted the total
tag when **no** component was found. Walmart reports the lease-amortization component but the
consolidated total under `DepreciationAmortizationAndAccretionNet`, which was never consulted.

## 2. Walmart independent benchmark verification (Task 2)

Retrieved XBRL facts (`DepreciationAmortizationAndAccretionNet`) vs the provided benchmarks
(USD millions):

| Period | Production | Benchmark | Match |
|---|---:|---:|---|
| FY2024 | 11,853 | 11,853 | ✅ |
| FY2025 | 12,973 | 12,973 | ✅ |
| FY2026 | 14,203 | 14,203 | ✅ |
| TTM ended 2026-07-31 | 15,093 | 15,093 | ✅ |

## 3. Walmart valuation rebuild (Task 3)

Identical dated financial + market inputs, isolating each correction (illustrative 10% WACC):

| Metric | A: orig debt + orig D&A | B: corrected debt + orig D&A | C: corrected debt + corrected D&A |
|---|---:|---:|---:|
| D&A / revenue driver | 0.13% | 0.13% | 1.93% |
| Year-1 FCFF | $0.246B | $0.246B | $13.58B |
| Terminal value | $2.35B | $2.35B | $129.95B |
| Enterprise value | $3.37B | $3.37B | $186.17B |
| Net debt | $35.24B | $45.71B | $45.71B |
| Equity value | −$31.87B | −$42.35B | +$140.46B |
| 5-year DCF/share | −$3.97 | −$5.28 | +$17.51 |
| Multi-stage DCF/share | +$18.38 | +$17.07 | +$26.18 |

- **A→B**: correcting debt alone makes equity *more* negative (−$31.87B → −$42.35B), because
  the D&A bug still collapses enterprise value to $3.37B.
- **B→C**: correcting D&A (0.13% → 1.93%) raises year-1 FCFF ~55×, EV $3.37B → $186.17B, and
  flips equity from −$42.35B to +$140.46B. This is the **dominant** driver of the recovery.

The D&A correction is a documented financial-accuracy fix (lease amortization → consolidated
D&A), **not** market-price tuning: the resulting intrinsic ($17.51 / $26.18) remains far below
the ~$132 market price, so no assumption was moved toward the market.

## 4. Cross-company D&A audit (Task 4)

`evidence/da_extraction_matrix.json` — 20 development companies:

| Status | Companies |
|---|---|
| **consolidated** (source-verified) | AMZN, AAPL, HD, NVDA, WMT, COST, KO, PG, MCD, CAT, UPS, DIS |
| **derived** (component reconstruction) | MSFT, TSLA, ORCL, AMD |
| **unavailable** (no reliable D&A) | GOOGL, NKE |
| **blocked** (extraction blocked) | XOM, JNJ |

Derived and unavailable/blocked companies are **not** claimed as verified.

## 5. Regression and acceptance (Task 5)

- `tests/test_da.py` — 6 tests: consolidated-vs-lease competition, component-only
  reconstruction, lease-amortization-alone → unavailable, total+component double-count,
  incomplete component coverage, and TTM tag-migration (stale-tag rejection).
- Full suite: **304 passed, 32 subtests passed**.
- 91/91 numerical comparisons: **PASS, max_diff 0.000000**.
- Independent recomputation of Walmart's corrected valuation (see §3) matches the deterministic
  engine; corrected D&A / forecast / valuation are consistent across the website and exports.

**Preserved:** checkpoint `2681a0b` and all historical outputs. No new valuation models, no
hardcoded financial amounts, no market-price tuning, no push/merge.

---

# Phase 2D.2 — D&A Recovery and Regression Prevention

Checkpoint: `efac79c` · Branch: `ai-financial-reconciliation`

## 1. Nike and Alphabet D&A recovered (Tasks 1–2)

`autoval/da.py` gained two **reusable** recovery paths (no ticker-specific hardcoding):

- **Cross-period tag migration** (Nike): an issuer that tagged its D&A line as `Depreciation`
  and later migrated to a combined total tag is merged, **validated by overlap equality**
  (`Depreciation` == total D&A in the years both are reported, confirming negligible
  amortization). Nike went `unavailable` → **consolidated**.
- **Component reconstruction with relaxed completeness + quarterly amortization** (Alphabet):
  the `Depreciation` completeness gate now requires the **trailing 3-year forecast window**
  (which is all the driver uses), not every year; intangible amortization reported only as
  3-month 10-Q increments is summed to fiscal years; finance-lease ROU amortization is added
  as a separate, non-overlapping component. Alphabet went `unavailable` → **derived**.

### Nike — LLM-verified (benchmarks used only for evaluation, never passed to the agent)

| Period | Production (now) | Benchmark | Match |
|---|---:|---:|---|
| FY2024 | 796 | 796 | ✅ |
| FY2025 | 775 | 775 | ✅ |
| FY2026 | 747 | 747 | ✅ |

LLM finding: consolidated D&A line = `DepreciationDepletionAndAmortization`; the older
`Depreciation` tag is the **pre-migration same line**, not a separate PP&E-only component.

### Alphabet — LLM-verified

LLM finding: `component_sum` = `Depreciation` (PP&E) + `AmortizationOfIntangibleAssets`
(intangible) + `FinanceLeaseRightOfUseAssetAmortization` (ROU). "Depreciation is not the
complete D&A figure; it is only the PP&E depreciation component." Production D&A FY2025 =
$22,064M (depreciation 21,136 + finance-lease 553 + 9-month amortization 375; the Q4
amortization increment is not yet tagged and is disclosed as remaining uncertainty).

## 2. Derived D&A validation (Task 3)

| Ticker | Reconstruction | Non-overlapping? | Complete? |
|---|---|---|---|
| MSFT | Depreciation 34,300 + Amortization 4,700 + Finance-lease 5,403 | ✅ | ✅ |
| TSLA | Depreciation 5,030 + Finance-lease 118 (amortization negligible/absent) | ✅ | ✅ |
| ORCL | Depreciation 7,623 + Amortization 1,671 + Finance-lease 351 | ✅ | ✅ |
| AMD | Depreciation 521 + Amortization 2,300 | ✅ | ✅ |

A `Depreciation` tag alone is **not** treated as complete D&A; the resolver requires the
distinct depreciation/amortization/ROU components and stays `derived` (not `verified`).

## 3. Regression prevention (Task 5)

20-company re-audit (`da_extraction_matrix.json`):

| Status | Count | Companies |
|---|---:|---|
| consolidated | 13 | AMZN, AAPL, HD, NVDA, WMT, COST, KO, PG, MCD, CAT, UPS, DIS, **NKE** |
| derived | 5 | MSFT, TSLA, ORCL, AMD, **GOOGL** |
| unavailable | 0 | — |
| blocked | 2 | XOM, JNJ |

- Full suite: **307 passed, 32 subtests passed**.
- 91/91 numerical comparisons: **PASS, max_diff 0.000000** (these use **preserved historical
  snapshots** in `evidence/batch_verify.py`, independent of the newly-corrected D&A extraction;
  both historical reproducibility and the new extraction pipeline are tested).
- New regression tests (`tests/test_da.py`): cross-period tag migration, partial
  depreciation-window reconstruction, quarterly amortization annualization, plus the prior
  consolidated-vs-lease / double-count / incomplete-coverage / TTM-migration tests.

## 4. Walmart acceptance evidence (Task 4)

The reported A/B/C valuation comparison is preserved (see §3 of the Phase 2D.1 section).
The fixed-WACC experiment (A→B, correcting debt only) is **separated** from the full
production recalculation (B→C, correcting D&A), which is the dominant driver. WACC
capital-structure weights, annual FCFF projections, terminal-value formulas and the
five-year/multi-stage DCF are computed by the deterministic engine and independently
recomputed to within $0.01/share; closeness to the market price is **not** used as evidence.

## 5. LLM execution (real, not mocked)

`evidence/phase2d2_da_agent.py` retrieved the original cash-flow-statement inline-XBRL facts
for Nike and Alphabet and ran a real `deepseek-v4-pro-0813` investigation. Both proposals
were **validated** and agree with the deterministic resolver. Records:
`evidence/reconciliation_records/NKE_*.json`, `GOOGL_*.json`.

**Preserved:** checkpoint `efac79c` and all historical outputs. No new valuation models, no
hardcoded financial amounts, no market-price tuning, no push/merge.

