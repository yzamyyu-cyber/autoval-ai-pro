# ORACLE CORP (ORCL) — Research Report

## Executive summary
REPORTED: Oracle Corp (ORCL) snapshot 2026-11-25. Reported balance-sheet items: cash and equivalents $36,369,000,000 [ORCL.cash_and_equivalents]; long-term debt $117,712,000,000 [ORCL.long_term_debt]; current portion of long-term debt $7,625,000,000 [ORCL.current_portion_long_term_debt]; finance lease liability $9,185,000,000 [ORCL.finance_lease_liability]; shares outstanding 3,023,736,000 [ORCL.shares_outstanding]. DERIVED: net debt $98,153,000,000 [ORCL.net_debt]. ASSUMED/ILLUSTRATIVE: DCF drivers and WACC are from provided deterministic tables, not reported guidance. INTERPRETATION: The driver-based five-year DCF is negative in all scenarios (Bear -$110.91, Base -$81.88, Bull -$53.05) and the multi-stage DCF ranges from -$9.90 to $53.49; with no market price ('vs price n/a'), no target price or rating is supported.

## Business and financial performance
REPORTED: Only balance-sheet/capital-structure data are provided. Cash $36.369B [ORCL.cash_and_equivalents]; long-term debt $117.712B [ORCL.long_term_debt]; current portion of long-term debt $7.625B [ORCL.current_portion_long_term_debt]; finance lease liability $9.185B [ORCL.finance_lease_liability]; shares outstanding 3.023736B [ORCL.shares_outstanding]. DERIVED: net debt $98.153B [ORCL.net_debt] = long-term debt + current portion + finance leases - cash. INTERPRETATION: The capital structure appears debt-heavy relative to reported cash; no reported revenue, operating income, net income, margins, or EPS are provided, so profitability and operating performance cannot be evaluated from reported facts.

## Revenue growth, profitability and reinvestment
ASSUMED MODEL DRIVERS: The provided deterministic driver table lists revenue growth 12.8%, operating margin 30.1%, tax rate 21.0%, D&A/revenue 12.3%, CapEx/revenue 48.3%, NWC/revenue -15.6%. These are not reported financials. DATA QUALITY FLAG: The evidence records [ORCL.revenue_growth], [ORCL.operating_margin], [ORCL.tax_rate], [ORCL.da_ratio], [ORCL.capex_ratio], and [ORCL.nwc_ratio] are each listed as 'estimated' with value 0, conflicting with the deterministic driver table. INTERPRETATION: CapEx/revenue at 48.3% is extremely high and likely drives negative near-term free cash flow; negative NWC/revenue means working capital is modeled as a source of cash rather than a use; these assumptions dominate the DCF.

## Five-year vs multi-stage DCF
DETERMINISTIC TABLE OUTPUTS: Five-year DCF intrinsic/share: Bear -$110.91, Base -$81.88, Bull -$53.05. Multi-stage DCF: Bear -$9.90, Base $17.74, Bull $53.49. 'vs price' is n/a because no market price was provided. INTERPRETATION: Negative five-year DCF values indicate that explicit forecast cash flows do not cover modeled reinvestment/capex. Multi-stage positive values in base/bull rely on terminal value beyond five years. Because valuation quality is unavailable and the five-year framework produces economically meaningless negative equity values, these outputs should be treated as low-confidence illustrations, not an actionable intrinsic value.

## WACC and terminal-value assumptions
ASSUMED: WACC 10.0% for all scenarios; terminal growth 1.5% Bear, 2.0% Base, 2.5% Bull; FCFF growth is driver-based. WACC basis is illustrative. LIMITATION: Forecast cash flows are discounted using full-year periods from the valuation date; no fractional fiscal-stub adjustment is applied. The normalized operating tax rate is a documented baseline, separate from the WACC marginal tax rate.

## Comparable valuation and reverse DCF
NOT AVAILABLE: No comparable company multiples, peer data, historical trading multiples, or market price were provided. A reverse DCF cannot be computed because there is no current market price and no target valuation multiple to solve for implied growth/margin assumptions. Therefore this section is not applicable with the provided data.

## Key valuation drivers and sensitivities
KEY DRIVERS: Revenue growth, operating margin, CapEx/revenue, D&A/revenue, NWC/revenue, WACC, and terminal growth. Scenario sensitivity from the deterministic tables: terminal growth ranges from 1.5% to 2.5%; multi-stage DCF moves from -$9.90 (Bear) to $53.49 (Bull); five-year DCF remains negative from -$110.91 to -$53.05. INTERPRETATION: Terminal value and CapEx/revenue are the dominant swing factors; the high CapEx/revenue ratio is a persistent value drag. No further sensitivity data were provided.

## Financial risks and model limitations
Valuation quality: unavailable. Data quality: none provided. Model limitations: driver-based FCFF forecast uses historical ratios/trends, not forward guidance; normalized operating tax rate is separate from WACC marginal tax rate; operating NWC ratio uses latest fiscal-year-end balance sheet (single point); driver ratios are assumed stable over five years; scenario spreads are rule-based; full-year discounting from valuation date without fractional fiscal-stub; intrinsic value and market price are non-contemporaneous; no automatic buy/sell/live trading. Additional data inconsistency: evidence records for drivers show value 0 while the deterministic driver table shows non-zero drivers. This further reduces confidence.

## Research conclusion
Based only on provided data, ORCL has reported cash $36.369B, long-term debt $117.712B, current portion $7.625B, finance leases $9.185B, and derived net debt $98.153B [ORCL.net_debt]. Shares outstanding are 3.023736B [ORCL.shares_outstanding]. The illustrative DCF outputs are not reliable: five-year DCF is negative in all scenarios and multi-stage DCF is highly sensitive to terminal growth; no market price is available. Therefore, I do not provide an unsupported headline valuation, price target, or rating. The evidence supports only a low-confidence, non-actionable conclusion until data inconsistencies are resolved and market/price/comparable data are supplied.

## Financial tables (deterministic)

| Scenario | Intrinsic/share | vs price | WACC | FCFF growth | Terminal g |
|---|---:|---:|---:|---:|---:|
| Bear | $-110.91 | n/a | 10.0% | driver | 1.5% |
| Base | $-81.88 | n/a | 10.0% | driver | 2.0% |
| Bull | $-53.05 | n/a | 10.0% | driver | 2.5% |

| Scenario | Five-year DCF | Multi-stage DCF |
|---|---:|---:|
| Bear | $-110.91 | $-9.90 |
| Base | $-81.88 | $17.74 |
| Bull | $-53.05 | $53.49 |

| Driver | Value |
|---|---:|
| Revenue growth | 12.8% |
| Operating margin | 30.1% |
| Tax rate | 21.0% |
| D&A / revenue | 12.3% |
| CapEx / revenue | 48.3% |
| NWC / revenue | -15.6% |

## Evidence records (deterministic)

| Evidence ID | Metric | Value | Verification |
|---|---|---:|---|
| `ORCL.shares_outstanding` | shares_outstanding | 3,023,736,000 | companyfacts |
| `ORCL.cash_and_equivalents` | cash_and_equivalents | 36,369,000,000 | companyfacts |
| `ORCL.long_term_debt` | long_term_debt | 117,712,000,000 | companyfacts |
| `ORCL.current_portion_long_term_debt` | current_portion_long_term_debt | 7,625,000,000 | companyfacts |
| `ORCL.finance_lease_liability` | finance_lease_liability | 9,185,000,000 | companyfacts |
| `ORCL.net_debt` | net_debt | 98,153,000,000 | derived |
| `ORCL.revenue_growth` | revenue_growth | 0 | estimated |
| `ORCL.operating_margin` | operating_margin | 0 | estimated |
| `ORCL.capex_ratio` | capex_ratio | 0 | estimated |
| `ORCL.da_ratio` | da_ratio | 0 | estimated |
| `ORCL.nwc_ratio` | nwc_ratio | -0 | estimated |
| `ORCL.tax_rate` | tax_rate | 0 | estimated |
