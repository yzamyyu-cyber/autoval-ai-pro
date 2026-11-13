# Microsoft (MSFT) — Base-Case DCF · Final Financial Verification

> Reproducible numerical explanation of the Base-case intrinsic value, sourced from the
> verified `outputs/workswarm_msft_v8/` run (no new market data retrieved). All amounts
> USD unless noted. Educational model; not an investment recommendation.

## 1. Key facts

| Item | Value |
|---|---|
| Company / ticker | Microsoft Corp (MSFT) |
| Market-price date | 2026-11-10 |
| Market close | $533.16 |
| Latest financial FY | 2026-06-30 |
| Forecast basis | Driver-based (Revenue → EBIT → NOPAT → FCFF) |
| Common / diluted shares | 7,426.2M / 7,453.0M |
| **Base intrinsic value / share** | **$235.25** |

## 2. Historical financial data (observed — SEC, FY2021–FY2026)

| FY end | Revenue | Operating income | D&A | CapEx |
|---|---:|---:|---:|---:|
| 2021-06-30 | $168.09B | $69.92B | $11.82B | $20.62B |
| 2022-06-30 | $198.27B | $83.38B | $15.58B | $23.89B |
| 2023-06-30 | $211.91B | $88.52B | $14.85B | $28.11B |
| 2024-06-30 | $245.12B | $109.43B | $21.80B | $44.48B |
| 2025-06-30 | $281.72B | $128.53B | $31.41B | $64.55B |
| 2026-06-30 | $331.84B | $155.24B | $44.40B | $115.95B |

## 3. Base-case forecast assumptions (derived, trailing 3-year)

| Driver | Base value | Derivation |
|---|---:|---|
| Revenue growth | **16.35%** | 3-yr revenue CAGR (331.84/245.12)^(1/2)−1 |
| Operating margin | **45.68%** | 3-yr mean of op-inc/revenue |
| Normalized tax rate | **21%** | documented baseline (not effective rate) |
| D&A % of revenue | **11.14%** | 3-yr mean |
| CapEx % of revenue | **25.33%** | 3-yr mean |
| NWC % of revenue | **−9.98%** | latest balance sheet (FY2026 year-end) |

## 4. Five-year forecast FCFF (Base, USD B)

| Year | Revenue | EBIT | NOPAT | D&A | CapEx | ΔNWC | **FCFF** |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 386.10 | 176.38 | 139.34 | 43.02 | 97.81 | −5.41 | **89.96** |
| 2 | 449.23 | 205.22 | 162.12 | 50.05 | 113.80 | −6.30 | **104.67** |
| 3 | 522.69 | 238.78 | 188.63 | 58.23 | 132.41 | −7.33 | **121.78** |
| 4 | 608.16 | 277.82 | 219.48 | 67.75 | 154.06 | −8.53 | **141.70** |
| 5 | 707.60 | 323.25 | 255.37 | 78.83 | 179.26 | −9.92 | **164.87** |

`FCFF = NOPAT + D&A − CapEx − ΔNWC` (NWC is negative, so ΔNWC < 0 adds cash flow).

## 5. Company-specific WACC (estimated)

| Input | Value | Source |
|---|---:|---|
| Risk-free rate | 4.998% | ^TNX (10-yr, FRED fallback) |
| Equity beta | 1.1238 | 5-yr weekly vs SPY |
| Equity risk premium | 4.46% | Damodaran implied |
| **Cost of equity** | **10.01%** | rf + β·ERP |
| Pre-tax cost of debt | 8.60% | interest ÷ gross debt (proxy) |
| Marginal tax | 21% | US federal baseline |
| After-tax cost of debt | 6.79% | 8.60%×(1−21%) |
| Equity weight / Debt weight | 99.11% / 0.89% | $3,959.3B / $35.5B |
| **WACC** | **9.98%** | |

## 6. DCF & enterprise-to-equity bridge (Base)

| Component | USD |
|---|---:|
| PV of forecast FCFF (Y1–Y5) | $459.17B |
| PV of terminal value (g=2.0%) | $1,309.34B |
| Terminal weight of EV | 74.0% |
| **Enterprise value (EV)** | **$1,768.51B** |
| − Net debt (debt $35.48B − cash $20.28B) | −$15.20B |
| = Equity value (cash-only) | $1,753.31B |
| ÷ Diluted shares | 7,453.0M |
| **Intrinsic value / share** | **$235.25** |

Investment-adjusted (bridge): eligible nonoperating securities = conservative $31.63B /
upper $44.23B / reconciled $40.23B → intrinsic **$239.49 / $241.18 / $240.65**.

## 7. Independent Decimal verification

Re-derived Base Year 1 with `decimal.Decimal` (30-digit) from the driver inputs:

| Line | Decimal (USD B) | Engine (USD B) | Abs. diff |
|---|---:|---:|---:|
| Revenue | 386.100170 | 386.100170 | 4.5e−5 |
| NOPAT | 139.339933 | 139.339933 | 8.1e−6 |
| FCFF | 89.958539 | 89.958539 | 1.8e−6 |

EV bridge: EV $1,768.514B − net debt $15.20B = equity $1,753.314B ÷ 7,453.0M shares =
**$235.249408** (engine $235.249408; diff 4.0e−15). Tolerance: <$0.01/share ✅.

## 8. Sensitivity analysis (from the verified output)

**WACC × terminal growth → intrinsic value/share (USD):**

| Terminal g \ WACC | 8.48% | 8.98% | **9.98%** | 10.98% | 11.48% |
|---|--:|--:|--:|--:|--:|
| 1.5% | 276 | 257 | 224 | 199 | 188 |
| **2.0%** | 294 | 272 | **235** | 207 | 195 |
| 2.5% | 315 | 289 | 248 | 217 | 204 |

**CapEx-intensity sensitivity:**

| Case | CapEx / revenue | Base intrinsic/share |
|---|---|---:|
| Base (3-yr mean) | 25.33% | $235.25 |
| Persistent high CapEx (FY2026) | 34.94% | $137.40 |
| 6-yr mean / median | 18.93% / 15.70% | — |

## 9. Notes

- **Observed vs forecast:** §2 is observed SEC data; §3–§4 are derived assumptions (not
  forward guidance). WACC is company-specific and estimated; only capex/terminal-growth and
  the scenario spread are illustrative policy.
- Intrinsic value is far below the $533.16 market price; the gap reflects the conservative
  WACC (~10%) and the high capex intensity relative to the market's growth expectations.
- Terminal value is 74% of EV — a known sensitivity of the model.
