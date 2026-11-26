# Valuation Integrity (Phase 6, Stage A)

Branch: `valuation-integrity-and-exports` (forked from `249b383`). Zero LLM calls.

## Negative DCF investigation (Task 1)

Amazon's evidence-backed CapEx (22–30%) applied **persistently** across the 5-year forecast
drives FCFF negative and the base DCF to −$73.31/share. The audit traced this to a
**forecast-horizon defect**, not an extraction or arithmetic error: elevated CapEx was applied
uniformly to every forecast year, ignoring that the cloud/AI build-out is a *temporary*
investment phase. (Revenue, margin, D&A, NWC, NOPAT, WACC, terminal growth, bridge and
share-count units were each checked and are consistent.)

## Time-dependent forecast assumptions (Task 2)

`apply_assumptions` now parses an explicit **horizon** per proposal and applies a temporary
CapEx elevation only over that horizon, then fades linearly back toward the historical driver
(never persisted into perpetuity). The multi-stage DCF still uses an ROIC-consistent terminal
(WACC > terminal growth validated).

| AMZN (base DCF/share) | Value |
|---|---:|
| Original 5-year DCF | $5.42 |
| Original multi-stage DCF | $48.19 |
| Persistent elevated CapEx (5-yr) | −$73.31 |
| **Horizon-aware (2-yr fade)** | **−$11.77** |

## Negative equity & model selection (Task 3)

One consistent presentation policy: negative modeled equity is never shown as a meaningful
negative share price; the headline is **"N/A — Model Review Required"** when base-case equity
is negative or material model limitations invalidate it. Signed mechanical values are retained
in labelled audit sections (never silently zeroed); misleading valuation-gap percentages are
suppressed. Bear/base/bull and five-year/multi-stage suitability are assessed independently;
a model is never chosen merely because it is positive or nearer market.

## Numerical acceptance (Task 4)

AMZN/MSFT historical vs evidence-backed forecasts are recomputed independently (see
`evidence/forecast_proposals_*.json`). ORCL, WMT and TSLA remain materially limited or
negative; no predictive-accuracy claim is made (no out-of-sample backtest).
