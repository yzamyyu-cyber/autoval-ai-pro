# Professional Release Acceptance (Phase 7)

Branch: `professional-release-candidate` (forked from `8157db1`). Zero LLM calls.

## Negative DCF acceptance (Task 1) — AMZN full comparison

Identical dated financial inputs; evidence-supported 2-year investment horizon vs assumed
5-year transition.

| Model | Five-year DCF | Multi-stage DCF |
|---|---:|---:|
| Original (historical drivers) | $5.42 | $48.19 |
| Persistent elevated CapEx (stress) | −$73.31 | $30.24 |
| **Horizon-aware (2-yr fade)** | **−$11.77** | **$46.73** |

The multi-stage DCF is stable because its ROIC-consistent terminal already fades
reinvestment; the five-year DCF is more distorted by a temporary investment phase. The
2-year fade is an **evidence-supported investment horizon**, not a verified mature
assumption; the transition length (5y) remains an assumed parameter. Terminal reinvestment,
terminal FCFF, enterprise value and the equity bridge were recomputed independently.

Negative mechanical equity (AMZN, ORCL, WMT, TSLA) appears only in labelled audit sections —
never as a meaningful share price or misleading downside percentage.

## Professional website (Task 2)

The existing navy/teal/neutral design is retained and made consistent: valuation cards,
financial charts, interactive forecast/sensitivity controls, comparable-company analysis, AI
Research Analyst, AI Financial Reconciliation, Financial Evidence Centre, and Excel/PDF
downloads. The offline demo runs on clearly labelled dated snapshots + cached AI reports with
no automatic paid LLM calls.

## Export acceptance (Task 3)

- **Excel** (`evidence/exports/{MSFT,AMZN,ORCL}_valuation.xlsx`): 11 sheets; FCFF forecast uses
  genuinely linked formulas (`FCFF = NOPAT + D&A − CapEx − ΔNWC`); evidence tables are static;
  assumptions are editable (blue) vs derived (black).
- **PDF** (`evidence/exports/{MSFT,AMZN,ORCL}_valuation.pdf`): five-year table, five-year vs
  multi-stage table, a valuation bar chart, and limitations — paginated and readable.
- Website, Excel, PDF, Markdown and JSON use the same selected company / snapshot / basis /
  approved assumptions.

## Website & product acceptance (Task 4)

Real Playwright (deterministic MSFT fixture): desktop + mobile, tab navigation, **0 page
errors**. Screenshots: `evidence/screenshot_{overview,multistage,research,evidence,mobile}.png`.

## Tests (Task 5)

`tests/test_exports.py` (4) + `tests/test_forecast_assumptions.py` (temporary-CapEx-horizon
fade). Full suite: **345 passed, 32 subtests passed**.

## API usage

0 LLM calls.

## Unresolved / limitations

- The 2-year CapEx fade is evidence-supported, not a verified mature assumption; the
  transition length remains an assumed parameter.
- ORCL/WMT/TSLA remain materially limited (negative equity) — reported as such, not tuned.
- PDF is a compact summary; full narrative lives in the Markdown research report.
