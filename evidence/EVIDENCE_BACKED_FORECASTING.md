# Evidence-Backed Forecasting (Phase 5)

Branch: `evidence-backed-forecasting` (forked from `ee0dd5a`).

## Phase 4 integration check (Task 1)

The production pipeline now calls `discover_peers` (automatic SIC fallback) instead of the
curated-only `peer_groups`, and stores the discovery result in `result["relative"]["discovery"]`.
The website's `render_peers` already renders the selection method + exclusion rationale. An
unmapped-company fixture (`tests/test_peer_selection.py::test_unmapped_sic_discovery`) confirms
SIC fallback. Amazon's retail / ecommerce / cloud / advertising groups remain separate and are
not presented as interchangeable segment valuations.

## Evidence-backed forecast assumptions (Task 2)

New `autoval/forecast_assumptions.py`:
- `investigate_assumptions(result, ua, chat_fn)` — retrieves guidance/MD&A/investment-plan
  note excerpts and produces structured proposals for revenue growth, operating margin, CapEx
  intensity, transition years and mature ROIC, each with original, proposed, source, filing
  date, justification, horizon, uncertainty, and `kind` (guidance vs interpretation).
- `validate_assumptions` — deterministic checks (driver, economic range, source, kind, and a
  look-ahead guard: evidence must not postdate the analysis snapshot date).
- `apply_assumptions` — regenerates the five-year + multi-stage DCF with approved assumptions,
  **preserving WACC, terminal growth and mature ROIC** (unless separately approved). Original
  financial facts/history are never mutated.

## Acceptance (Task 5) — AMZN + MSFT (2 LLM calls)

| Company | Proposals | Validation | Applied result (base DCF/share) |
|---|---|---|---|
| AMZN | revenue growth 12–16%, margin 11.5–14%, CapEx 22–30% | validated | $5.42 → **−$73.31** |
| MSFT | drivers ≈ historical (no material change) | validated | $163.81 → $163.81 |

**Key finding — AMZN temporary investment intensity:** applying the elevated CapEx intensity
(22–30% vs historical 13.7%) *persistently* across the five-year forecast drives FCFF negative
and equity negative (−$73.31/share). The economically consistent treatment is to fade this
build-out through the multi-stage transition (ROIC-consistent terminal) rather than persist it
into perpetuity — exactly the reinvestment tension the model-limitation policy already flags.
MSFT's investigation found no material evidence to move its historical drivers.

**Backtest:** historical point-in-time evidence is not available for these fixtures, so the
forecast-error backtest is reported as **unexecuted** (no predictive-accuracy claim is made).

## Website (Task 4)

"Evidence-backed Forecast" section added to the AI Research Analyst tab: current vs proposed
assumptions, source references, approve/reject controls, original vs adjusted DCF, and cache
keyed by company × snapshot × assumptions × prompt/model version. No automatic LLM call on
rerun.

## Tests (Task 5)

`tests/test_forecast_assumptions.py` (9 tests): invalid range, unsupported driver, missing
source, stale/look-ahead evidence, WACC/terminal/ROIC preservation, capex DCF change,
unauthorized-driver ignored, mocked investigation. Full suite: **340 passed, 32 subtests**.

## API usage

2 LLM calls (AMZN + MSFT). No token/cost metering exposed by the endpoint.

## Limitations

- Fixture snapshots carry balance-sheet/forecast evidence only; guidance excerpts are from the
  latest 10-Q. No analyst-consensus fabrication.
- AMZN's persistent-investment scenario is shown as a mechanical negative-equity outcome, not
  tuned toward any market price.
