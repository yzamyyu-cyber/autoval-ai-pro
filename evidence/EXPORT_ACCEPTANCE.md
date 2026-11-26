# Export Acceptance (Phase 6, Stage B)

Branch: `valuation-integrity-and-exports`.

## Excel valuation workbook (Task 5)

`autoval/exports.py::build_excel_workbook` produces a formula-driven `.xlsx` with sheets:
Executive Summary, Historical Financials, Forecast Assumptions, FCFF Forecast (linked
`FCFF = NOPAT + D&A − CapEx − ΔNWC` formulas), WACC Calculation, Five-Year DCF, Multi-Stage
DCF, Sensitivity Analysis, Comparable Companies, Financial Evidence, and Model Limitations.
Reported facts / assumptions / derived calculations are labelled; negative residuals are
retained in audit columns but the headline is suppressed for negative-equity models.

Generated: `evidence/exports/{MSFT,AMZN,ORCL}_valuation.xlsx`.

## PDF research report (Task 6)

`build_pdf_report` produces a paginated PDF (company, headline, scenario table, limitations)
using cached deterministic data only — no LLM calls. Generated:
`evidence/exports/{MSFT,AMZN,ORCL}_valuation.pdf`.

## Website (Task 7)

"Excel valuation workbook" and "PDF research report" download buttons added to the Evidence &
Exports tab (deterministic, no LLM).

## Verification

- `tests/test_exports.py` (4 tests): sheet completeness, base-DCF reproduction, PDF generation,
  negative-equity headline suppression.
- `tests/test_forecast_assumptions.py` extended with a temporary-CapEx-horizon-fade test.
- Full suite: **345 passed, 32 subtests passed**.
- openpyxl + reportlab added to `requirements.txt`.

## API usage

0 LLM calls.
