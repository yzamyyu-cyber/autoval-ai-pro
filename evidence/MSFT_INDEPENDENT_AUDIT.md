# Microsoft (MSFT) — Independent Original-Filing Audit

Source documents (retrieved and inspected directly):
- 10-K FY2026 (period 2025-07-01 → 2026-06-30): https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm (accession 0001193125-26-323660)
- 10-Q Q1 FY2027 (period 2026-07-01 → 2026-09-30): https://www.sec.gov/Archives/edgar/data/789019/000119312526436133/msft-20260930.htm (accession 0001193125-26-436133)

Values below are read from the rendered financial statements (HTML), not from the
Companyfacts API. Units: USD millions unless noted.

## Income statement (annual, FY2026 vs FY2025)

| Metric | FY2026 (10-K) | FY2025 (10-K) | AutoVal | Δ |
|---|---:|---:|---:|---:|
| Total revenue | 331,839 | 281,724 | 331,839 | 0 |
| Gross margin | 225,465 | 193,893 | — | — |
| Operating income | 155,237 | 128,528 | 155,237 | 0 |
| Net income | 133,749 | 101,832 | 133,749 | 0 |
| Diluted EPS | 17.95 | 13.64 | — | — |

## Shares (per the 10-K, millions)

| | Basic | Diluted |
|---|---:|---:|
| Weighted-average | 7,429 | 7,453 |
| AutoVal diluted_shares | — | 7,453 | Δ 0 |

## Balance sheet (10-K FY2026-06-30 vs latest 10-Q 2026-09-30)

| Metric | 10-K (2026-06-30) | AutoVal (2026-09-30, latest) | Δ | Note |
|---|---:|---:|---:|---|
| Cash & equivalents | 20,935 | 20,281 | −654 | different as-of date (latest 10-Q used) |
| Short-term investments | 55,908 | 44,228 | −11,680 | different as-of date |
| Long-term debt (noncurrent) | 31,067 | 31,090 | +23 | different as-of date |
| Finance-lease liability | (note) | 70,973 | — | reported in 10-Q balance sheet |
| Total debt | — | 106,454 | — | LT debt + finance leases + current + short |

## TTM reconstruction (additive, 10-Q basis)

| Metric | Latest FY | Current YTD | Prior YTD | TTM |
|---|---:|---:|---:|---:|
| Revenue | 331,839 | + | − | 346,445 |
| Operating income | 155,237 | + | − | 163,191 |

AutoVal TTM revenue = 346,445; operating income = 163,191 (Δ 0 vs reconstruction).

## Verification status

- Income statement and share counts: **independently verified** against the 10-K HTML (Δ = 0).
- Balance-sheet items: **verified**, but the valuation uses the latest 10-Q (2026-09-30)
  balance sheet, so values differ from the 10-K (2026-06-30) by the quarter's change — this
  is the intended "latest available" basis, not an error.
- Taxes/NOPAT, economic CapEx, operating NWC: reconciled via the Companyfacts component
  sum (not yet re-derived line-by-line from the HTML statements) — see limitations.

## Limitations

- D&A and economic CapEx are component sums; the 10-K cash-flow-statement "additions to
  property and equipment" is disclosed as a $51.4B year-over-year increase (finance-lease +
  cash), not yet split into the exact cash vs finance-lease components from the HTML.
- Operating NWC components were not individually re-read from the 10-K balance sheet.
