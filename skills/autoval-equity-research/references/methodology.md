# Method definitions and caveats

## Historical FCFF (cash-flow cross-check)

`FCFF = CFO − cash CapEx + cash_interest_paid × (1 − eff.tax)` — the CFO-based cross-check
uses **cash interest paid** where tagged, else interest expense (labeled proxy). This is a
*reference* figure, not the driver-forecast input.

## Driver-based five-year forecast

Per year: `Revenue_t = Revenue_{t−1} × (1 + g)`, `EBIT = Revenue × margin`,
`NOPAT = EBIT × (1 − normalized_tax)`, `D&A = Revenue × da_ratio`,
`CapEx = Revenue × capex_ratio`, `NWC = Revenue × nwc_ratio`, `ΔNWC = NWC_t − NWC_{t−1}`,
`FCFF = NOPAT + D&A − CapEx − ΔNWC` (an increase in NWC reduces FCFF).

Drivers are trailing-3-year historical ratios/trends (revenue CAGR, operating margin,
D&A/CapEx % of revenue) plus a documented 21% normalized-tax baseline. Bear/Base/Bull vary
revenue growth and margin (±3pp) and D&A/CapEx intensity; a separate CapEx-intensity
sensitivity holds the latest-year capex ratio. A CapEx/terminal-growth/WACC sensitivity
grid is also produced.

## Company-specific WACC

`Re = rf + β·ERP`; `WACC = We·Re + Wd·Rd_at` where `Rd_at = pre-tax cost of debt × (1 −
marginal_tax)`. Risk-free from FRED DGS10 (`^TNX` fallback), β from a 5-yr weekly
regression vs SPY (2-yr secondary), ERP from Damodaran implied ERP, cost of debt from
interest/avg-debt (proxy), and a 21% US-federal marginal-tax baseline. WACC must exceed
terminal growth. WACC is **company-specific and estimated**, not illustrative; only the
capex/terminal-growth/scenario-spread inputs are illustrative policy.

## Enterprise-to-equity bridge

`EV = market cap + gross debt + finance leases + preferred + minority − cash`, plus eligible
nonoperating securities reported as a conservative/upper range (reconciled only when the
restricted-in-short-term note is verified). Equity = EV − net debt; per-share uses the
diluted share count (point-in-time common shares are used for market cap).

## Relative valuation (P/E and EV/EBITDA)

GAAP trailing diluted P/E = price ÷ TTM diluted EPS (net income ÷ time-weighted TTM diluted
shares). `EBITDA = operating income + verified D&A` (prefer a single total-D&A tag; never
add a total and its components). EV/EBITDA uses the same EV convention. Peer medians/P25/P75
→ implied target price ranges. P/E is more reliable than EV/EBITDA because debt and D&A XBRL
tags vary by issuer.

## Technical and verification

SMA20 > SMA50 traded next bar (10 bps/trade) vs buy-and-hold, in-sample only.
`verify_output.py` recomputes the DCF (constant-growth and driver-based) with `Decimal`
arithmetic to within $0.01/share. Automated tests cover finance, SEC, forecast, WACC and
relative-valuation logic.
