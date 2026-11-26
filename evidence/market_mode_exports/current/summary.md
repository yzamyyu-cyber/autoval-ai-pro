# AutoVal AI — MSFT (live)

> MICROSOFT CORP

Data mode: **live** · Market-data mode: **current** · Price as of: 2026-11-10 · Financial FY: 2026-06-30

Latest available market close: **$533.16** per share (not necessarily real-time).

| DCF case | Intrinsic per share (USD) | Upside vs close | WACC | FCFF growth | Terminal g |
|---|---:|---:|---:|---:|---:|
| Bear | $76.78 | -85.6% | 9.8% | driver | 1.5% |
| Base | $163.81 | -69.3% | 9.8% | driver | 2.0% |
| Bull | $260.56 | -51.1% | 9.8% | driver | 2.5% |

## Enterprise-to-equity bridge

- Operating enterprise value (base): $1,307,028,582,141
- Total debt: $106,454,000,000 · Cash: $20,281,000,000
- Short-term investments: $44,228,000,000 · Restricted (total): $12,600,000,000
- Eligible nonoperating securities — conservative: $31,628,000,000 · upper: $44,228,000,000
- Upper bound is NOT a verified valuation; reconciled case requires note verification.

## Technical backtest (illustrative, in-sample)

- SMA20 > SMA50: Hold
- Strategy: +0.00%
- Buy-and-hold (same period): +0.00%
- Cost: 10.0 basis points per position change

## Source and caveats

- Financial source: SEC EDGAR XBRL companyfacts
- Financial URL: https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json
- Market source: fixture (genuine live close)
- WACC assumption: Company-specific WACC (single rate across scenarios)

This output is a reproducible educational model, **not an investment recommendation**. Check `analysis.json` for complete assumptions, dates, source tags and limitations.
