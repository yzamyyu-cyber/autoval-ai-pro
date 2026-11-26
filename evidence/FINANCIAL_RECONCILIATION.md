# Financial Reconciliation

Independent source-data verification for the AutoVal AI Pro release candidate.
All USD figures in millions unless noted. "AutoVal value" is the extracted value;
"difference" is AutoVal minus source. Status = `reconciled` when difference ≈ 0.

## TTM revenue (additive: FY + current YTD − prior-year-comparable YTD)

| Ticker | TTM revenue ($M) | Basis | Period end | Verified |
|---|---:|---|---|---|
| AMZN | 797,455 | ttm | 2026-09-30 | ✓ (matches Q3 2026 filing) |
| MSFT | 346,445 | ttm | 2026-09-30 | ✓ |
| HD | 171,222 | ttm | 2026-11-01 | ✓ (52/53-week calendar) |
| AAPL | 478,834 | annual | FY end = latest qtr | ✓ (no newer quarter) |
| GOOGL | 471,098 | ttm | 2026-09-30 | ✓ |
| TSLA | 103,570 | ttm | 2026-09-30 | ✓ |
| NVDA | 302,970 | ttm | 2026-07-26 | ✓ (fiscal Q2) |

## AMZN reference figures (Q3 2026, USD M)

| Metric | Source (filing) | AutoVal | Δ |
|---|---:|---:|---:|
| TTM revenue | 797,455 | 797,455 | 0 |
| TTM operating income | 104,366 | 104,366 | 0 |
| TTM operating cash flow | 168,300 | 168,300 | 0 |
| Gross cash PP&E (TTM) | 215,192 | 215,192 | 0 |
| PP&E proceeds & incentives | 4,535 | (not netted — one-off) | n/a |
| Net cash PP&E | 210,657 | — | n/a |
| Finance-lease additions | 4,543 | 4,543 | 0 |
| Reported FCF | −42,357 | −46,892 (gross basis) | −4,535 |

## MSFT corrected valuation (the $85.92 defect)

| Stage | Revenue basis ($M) | Base DCF/share |
|---|---:|---:|
| Incorrect (prior-comparable = Q3 FY2026) | 182,286 | $85.92 |
| Correct (prior-comparable = Q1 FY2026) | 346,445 | **$171.70** |

See `VALUATION_REFERENCE.md` for the numerical input-to-output bridge.

## Source-discrepancy investigation (3 mismatches resolved)

All three were **reference-script tag-selection defects**, confirmed against original
companyfacts (accession-level) — NOT production-extraction errors.

| Ticker | Metric | Wrong (single tag) | Correct (tuple) | Root cause |
|---|---:|---:|---|
| GOOGL | revenue | $359,713M | $471,098M | `RevenueFromContractWithCustomerExcludingAssessedTax` is stale/partial; consolidated total is under `Revenues` (Q3 2026 YTD $357,269M, 272-day) |
| NVDA | revenue | $26,914M | $302,970M | same: `Revenues` is the total (FY2026 $215,938M + Q2 FY2027 YTD $177,837M); the single tag surfaced a quarter/partial |
| AAPL | capex | $9,571M | $9,041M | capex is `PaymentsToAcquirePropertyPlantAndEquipment` (FY2026 $9,041M); `PaymentsToAcquireProductiveAssets` is absent |

The production engine uses tag tuples with fallback (`_REVENUE_TAGS = (…ContractWithCustomer…, Revenues)`,
capex `(…ProductiveAssets, …PropertyPlantAndEquipment)`), which the original filings confirm is correct.
After correcting the reference script's tag resolution, reconciliation is **28 PASS, 0 MISMATCH**
(10 derived, 4 unavailable where a tag is genuinely absent).

## Original-filing verification (independent reference figures, USD millions)

| Company | Metric | Additive reconciliation | = | Filing URLs (accession) |
|---|---|---:|---|---|
| GOOGL | TTM revenue | 402,836 + 357,269 − 289,007 | 471,098 | goog-20251231.htm (10-K), goog-20260930.htm (10-Q) |
| AAPL | FY2026 cash PP&E | — | 9,041 | aapl-20260926.htm (10-K) |
| NVDA | TTM revenue (10-Q basis) | 215,938 + 177,837 − 90,805 | 302,970 | nvda-20260125.htm (10-K), nvda-20260726.htm (10-Q) |
| NVDA | TTM revenue (Q3 FY2027 release) | 215,938 + 293,681 − 147,811 | 361,808 | supplementalfinancialinfor.htm (8-K, 2026-11-17, Item 2.02) |

These are independent verification references (not hardcoded into the app). The Companyfacts
additive reconciliation reproduces the 10-Q-basis figures exactly (28 PASS, 0 MISMATCH).

## Data freshness (new)

`autoval/freshness.py::check_freshness()` detects newer 8-K earnings releases (Item 2.02)
beyond the latest 10-K/10-Q:

| Ticker | Latest periodic filing | Newer earnings release | fresh |
|---|---|---|---|
| NVDA | 2026-08-26 (10-Q) | 2026-11-17 (8-K Item 2.02) | **False** |
| MSFT | 2026-10-28 | 2026-10-28 | True |
| AMZN | 2026-10-30 | 2026-10-29 | True |

Policy: retain the latest complete periodic-filing valuation and display a
"newer results available" notice; earnings-release valuations are only used when all
essential inputs reconcile (prevents look-ahead bias).
