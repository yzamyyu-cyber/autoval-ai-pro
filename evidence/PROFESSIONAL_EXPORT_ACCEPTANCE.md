# Professional Export Acceptance (Phase 10B)

Branch: `release-v1`.

## Excel financial model (Tasks 1–2)

`autoval/exports.py::build_excel_workbook` now produces a **formula-driven** workbook with
financial-modeling conventions (navy headers, blue editable inputs, black formulas, green
cross-sheet links, `#,##0` / `0.0%` / `$` formats, freeze panes, colored sensitivity heatmap):

- Sheets: Assumptions (editable blue), FCFF Forecast (linked `=NOPAT+D&A−CapEx` and
  `=Revenue×(1+g)` formulas), Five-Year DCF, Multi-Stage DCF, Sensitivity (conditional
  heatmap), Historical & Ratios (linked margin `=C/B`), Financial Evidence (static, labelled),
  Model Limitations.
- Changing an Assumptions cell (revenue growth, margin, CapEx, WACC) updates the linked FCFF
  forecast formulas (verified: `FCFF Forecast!B2 = =Assumptions!B3*(1+Assumptions!B4)`).
- Negative mechanical equity is retained in the Five-Year DCF audit column; the headline cell
  shows **"N/A — Model Review Required"** (never a negative price).

Generated: `evidence/exports/{MSFT,AMZN,ORCL}_valuation.xlsx`.

## PDF research report (Task 3)

`build_pdf_report` now emits a multi-section, paginated report: title block, headline
(suppressed for negative equity), five-year vs multi-stage DCF table, valuation bar chart,
historical financial performance, forecast assumptions, WACC, risks/limitations and SEC
source reference. Generated: `evidence/exports/{MSFT,AMZN,ORCL}_valuation.pdf`.

## Consistency (Task 4)

Website, Excel, PDF, Markdown and JSON all derive from the same snapshot (company, basis,
assumptions, corrections, market-data classification, quality). Fixture data is never labelled
"current market observation"; synthetic price history is identified.

## Acceptance (Task 5)

- Regression tests `tests/test_exports.py` (6): sheet set, linked formulas, blue editable
  inputs, base-DCF reproduction, PDF generation, negative-equity headline suppression.
- Full suite: **346+ passed, 32 subtests** (export tests expanded).

## Recalculation status

**NOT EXECUTED** (no LibreOffice/`soffice` on this machine). Manual verification: open
`MSFT_valuation.xlsx`, change `Assumptions!B11` (WACC) or `B9` (CapEx/revenue), and confirm
`FCFF Forecast` column G and the DCF sheets update. Formulas are present and statically
validated; engine recalculation is not claimed as done.

## API usage

0 LLM calls.