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

## Valuation quality classification

`autoval/quality.py` labels each result with three states:

- **available** — required inputs present and reconciliation checks pass.
- **low_confidence** — data-quality concerns (company WACC unavailable in live mode, debt
  split assumed/stale, consolidated share-count approximation, small history) mean the
  value should not be presented as a reliable headline estimate. The mechanical estimate
  is preserved for audit.
- **unavailable** — required inputs invalid (all-forecast FCFF non-positive, missing shares,
  no analysis). Never substituted with zero.

Data-quality concerns and **model-risk warnings** are kept separate. Model-risk heuristics
(negative first-year FCFF, non-positive forecast revenue growth, terminal value above
`TERMINAL_WEIGHT_LIMIT`) are surfaced as warnings on every view but never suppress a
valuation on their own. The thresholds are configurable module constants (override
per-call), treated as review heuristics rather than financial formulas. The market-price
gap is never a signal. Exports that predate this feature (no `quality` field) are labeled
**"Not assessed"** and are not assumed to have passed the policy.

## Multi-stage DCF

The single-stage driver forecast holds capital intensity (hence the implicit reinvestment
rate) constant into perpetuity. `autoval/multistage.py` is a separate, additive model:

- **Years 1–5** — the existing driver-based FCFF forecast (unchanged).
- **Years 6–10** — revenue growth, operating margin and the reinvestment rate fade
  linearly from the explicit-forecast values to sustainable mature values.
- **Year 11+** — ROIC-consistent terminal:
  `reinvestment rate = terminal growth / mature incremental ROIC`;
  `terminal FCFF = year-11 NOPAT × (1 − reinvestment rate)`;
  `terminal value = terminal FCFF / (WACC − terminal growth)`.

The **mature incremental ROIC (12% default) is an assumed parameter**, not a
market-calibrated value; ROIC sensitivity is reported at 8/10/12/15/20% (values ≤ terminal
growth are rejected). The model validates `0 < ROIC < 1`, `ROIC > terminal growth` and
`WACC > terminal growth`. It does not change the original five-year DCF and is never
required to produce a higher valuation.

## Finance-lease accounting

Finance-lease liabilities are a debt-like claim and are included exactly once across the
DCF bridge, WACC debt and relative valuation. Economic CapEx = cash CapEx + finance-lease
additions (`RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability`), consistent with
D&A which already includes finance-lease ROU amortization. Operating leases are not
treated as finance leases. The cost-of-debt numerator (nonoperating interest expense) and
denominator (finance-lease-inclusive debt) use the same definition. Unresolved material
lease definitions are flagged as low confidence.

## Model-suitability interpretation

An implied terminal incremental ROIC below WACC is reported as **value-destructive
reinvestment** and a model-risk concern — it is *not* automatically labeled economically
impossible, because a short-term reinvestment phase (e.g. an AI/data-center build-out)
can legitimately earn below-hurdle returns before maturing. The single-stage model's
constant capital intensity becomes *genuinely inconsistent* only when that elevated
reinvestment rate is held into perpetuity alongside low terminal growth (implied
incremental ROIC ≪ WACC). The multi-stage model resolves this by fading the reinvestment
rate to `g / ROIC`.

Negative modeled equity is a mechanical artifact (discounted cash flows below net debt).
It is shown as "N/A — Negative modeled equity" in tables and charts and omitted from
charts (never as a zero or negative stock price); the signed value is preserved in the raw
export and audit details.

## TTM financial basis

The latest trailing-twelve-month period is the default forecast basis. TTM is computed
additively as `latest completed FY + current YTD − prior-year-comparable YTD`, robust to
cumulative 10-Q facts, rolling 12-month disclosures (excluded), single-quarter Q4 omission
and 52/53-week fiscal calendars. An Annual / Latest-TTM selector drives every view; the
annual-based DCF is retained as a comparison benchmark. Forecast cash flows are discounted
using full-year periods from the valuation date (a rolling-forward simplification — no
fractional fiscal-stub adjustment); intrinsic value and the delayed market price are
therefore non-contemporaneous approximations. TTM diluted EPS uses a duration-weighted
average of quarterly diluted shares and is labeled "reconstructed"; P/E is suppressed when
TTM earnings or diluted shares cannot be reconciled.
