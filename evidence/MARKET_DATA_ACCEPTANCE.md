# Market-Data Final Acceptance Audit

Status: **PASS** — all four market-data modes verified end-to-end against the committed code
(branch `financial-evidence-centre`, latest local commit `c2cc888` at audit start).

This document records **actual execution results** for the current working tree. No prior
completion summaries are relied upon.

---

## 1. Production behavior under four conditions (Task 1)

The production `build_analysis` live path was exercised through all four conditions using the
deterministic fixture harness (`tests/provider_fixture.py`) that runs the **real**
`analyze_driver_valuation` and the **real** Streamlit app — only the network boundaries are
substituted.

### Production JSON excerpts (per mode)

| Field | current | saved | illustrative | missing |
|---|---|---|---|---|
| `market_mode` | `current` | `saved` | `illustrative` | `missing` |
| `analysis.market_price` | `533.1599…` | `533.1599…` | `null` | `null` |
| `analysis.price_date` | `2026-11-10` | `2026-11-10` | `null` | `null` |
| `illustrative_market_price` | `null` | `null` | `533.1599…` | `null` |
| `wacc_basis` | `company-specific` | `company-specific` | `illustrative` | `unavailable` |
| `provenance.market.mode` | `current` | `saved` | `illustrative` | `missing` |
| base intrinsic/share | `163.807…` | `163.807…` | `163.807…` | `163.807…` |
| base `upside_vs_price_pct` | `-69.28%` | `-69.28%` | `null` | `null` |

### Assertion results

1. **Provider failure defaults to `missing`** — PASS. `resolve_market` catches the provider
   exception and returns `mode="missing"`; it never auto-substitutes illustrative inputs.
2. **No hypothetical price / market cap as a genuine observation** — PASS. In `illustrative` and
   `missing` modes `analysis.market_price` is `null`, `observed_multiples` returns
   `market_enterprise_value_usd = null`, and the hypothetical price is held in the separate
   `illustrative_market_price` field only.
3. **WACC classification reflects input provenance** — PASS. `classify_wacc` yields
   `company-specific` only when beta **and** equity value are genuine observations; otherwise
   `illustrative` (assumed inputs) or `unavailable` (missing inputs).
4. **Forward DCF gating** — PASS. The forward (financial-statement-driven) DCF computes an
   intrinsic value in every mode (financials are genuine); it never depends on the market price.
   `analyze_valuation` (constant-growth) and the TTM loop are now `null`-safe for the price.
5. **Reverse DCF requires genuine, dated observations** — PASS. `reverse_dcf` now raises a
   `ValueError` when `market_mode` is not `current`/`saved` (demo exempt), and the website
   `Market Expectations` tab suppresses the tool in non-genuine modes.
6. **Peer-implied valuations use only valid required inputs** — PASS. Peer P/E and EV/EBITDA are
   computed from genuine positive peer multiples + target TTM fundamentals (not the target price);
   in non-genuine modes the target's own market multiples are suppressed via
   `target_market_mode`.
7. **Genuine historical prices remain dated observations** — PASS. `saved` mode carries a genuine
   price + observation date (`price_date = 2026-11-10`).
8. **Website illustrative selection** — PASS. A "Market data source" selector (Live / Saved
   snapshot / Illustrative) was added to the research controls; it drives
   `build_analysis(…, market_mode=…)`, not just an environment variable.

Changed production files: `autoval/market_data.py`, `autoval/pipeline.py`,
`autoval/finance.py`, `autoval/reverse.py`, `autoval/relative_data.py`, `autoval/report.py`,
`app.py`.

---

## 2. Browser and export acceptance (Task 2)

### AppTest (deterministic, offline)

`tests/test_market_mode_app.py` — 5 tests (4 subtests) assert, for each mode, no unhandled
exception, correct price display, and reverse-DCF gating. **All pass.**

### Playwright (real Chromium browser)

`evidence/market_mode_browser_test.py` launched the real Streamlit server once per mode and
captured full-page screenshots. Company switching (Home Depot), Annual/TTM switching, Scenario
Lab, Multi-stage DCF, Market Expectations, Financials, Evidence & Exports and Compare Companies
were exercised in the `current` run.

| Screenshot | File | page errors |
|---|---|---|
| current | `evidence/market_mode_current.png` | 0 |
| saved | `evidence/market_mode_saved.png` | 0 |
| illustrative | `evidence/market_mode_illustrative.png` | 0 |
| missing | `evidence/market_mode_missing.png` | 0 |
| compare | `evidence/market_mode_compare.png` | 0 |

### Export inspection

`evidence/market_mode_export_check.py` generated Markdown, JSON, verification JSON, evidence CSV
and `save_analysis` outputs (`summary.md`, `technical.csv`, `forecast.csv`) for all four modes,
then asserted the exported values agree with the website display.

| mode | market_mode | price | wacc_basis | price_date | agree |
|---|---|---|---|---|---|
| current | current | 533.16 | company-specific | 2026-11-10 | ✔ |
| saved | saved | 533.16 | company-specific | 2026-11-10 | ✔ |
| illustrative | illustrative | null | illustrative | null | ✔ |
| missing | missing | null | unavailable | null | ✔ |

Exports live under `evidence/market_mode_exports/<mode>/`.

---

## 3. Mandatory numerical verification (Task 3)

Executed `SEC_USER_AGENT=… .venv/bin/python evidence/batch_verify.py` against the **current
commit** (re-fetched SEC facts, recomputed independently without importing the valuation
functions).

```
total=91 passed=91 failed=0 unavailable=0 max_diff=0.000000
```

`evidence/reference_comparison.csv` now holds **91 rows, 91 PASS**.

Complete automated test suite:

```
258 passed, 32 subtests passed
```

---

## 4. Changed files and remaining limitations

**Changed files**
- Production: `app.py`, `autoval/finance.py`, `autoval/market_data.py`, `autoval/pipeline.py`,
  `autoval/relative_data.py`, `autoval/report.py`, `autoval/reverse.py`
- Tests/harness: `tests/provider_fixture.py`, `tests/test_market_data.py`,
  `tests/test_market_data_pipeline.py`, `tests/test_market_mode_app.py`
- Evidence: `evidence/reference_comparison.csv`, `evidence/market_mode_browser_test.py`,
  `evidence/market_mode_export_check.py`, `evidence/market_mode_{current,saved,illustrative,missing,compare}.png`,
  `evidence/market_mode_exports/`

**Remaining limitations**
- The four-mode browser/export exercise uses deterministic sanitized fixtures (offline); the live
  `current` path still requires yfinance / SEC EDGAR / FRED / Damodaran network availability, and
  a provider failure correctly degrades to `missing`.
- `batch_verify.py` requires `SEC_USER_AGENT` and SEC network access; it was executed successfully
  with a test contact identifier.
- No new financial models were introduced (no SOTP / Monte Carlo). Prior commits and historical
  outputs are preserved.

**Preserve previous commits and historical outputs; this work is committed locally and is not
pushed or merged.**
