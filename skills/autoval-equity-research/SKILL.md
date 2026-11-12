---
name: autoval-equity-research
description: Run and independently verify a ticker-only U.S. equity valuation — automatic SEC retrieval, driver-based five-year FCFF DCF, company-specific WACC, investment-adjusted equity bridge, P/E and EV/EBITDA relative valuation, technical indicators, and Decimal-based independent verification. No trading or investment advice.
---

# AutoVal Equity Research — Regular WorkSwarm Skill

## Overview

A reproducible, ticker-only equity-research pipeline for U.S.-listed **nonfinancial** SEC
filers. Enter a ticker; the workflow retrieves filings and market data, then produces a
multi-method valuation with source dates and assumptions kept visible. All valuation math
is deterministic Python; the model must not invent figures.

## Capabilities

1. **SEC retrieval** — annual + quarterly XBRL facts (revenue, operating income, D&A,
   capex, debt, cash, leases, shares, diluted shares, interest, taxes).
2. **Driver-based DCF** — five-year forecast `Revenue → EBIT → NOPAT → FCFF`
   (`NOPAT + D&A − CapEx − ΔNWC`), Bear/Base/Bull scenarios, plus a CapEx-intensity
   sensitivity and a WACC×terminal-growth sensitivity grid.
3. **Company-specific WACC** — `rf + β·ERP` (FRED/`^TNX` risk-free, 5-yr weekly beta vs SPY,
   Damodaran implied ERP), debt-weighted, with a documented marginal-tax baseline.
4. **Enterprise-to-equity bridge** — `EV = mcap + gross debt + finance leases + preferred +
   minority − cash`, with eligible nonoperating securities reported as a
   conservative/upper (and note-verified reconciled) range.
5. **Relative valuation** — GAAP trailing P/E and EV/EBITDA peer comparison (median/P25/P75
   and implied price ranges) for configured peer groups.
6. **Technical indicators** — SMA 20/50/200 and a next-bar SMA-cross backtest vs buy-and-hold.
7. **Independent verification** — `verify_output.py` recomputes the DCF with `Decimal`
   arithmetic; `pytest`/`unittest` regression suite.

## Inputs

- **Project root** — the folder containing `run_analysis.py` / `verify_output.py` (the
  Skill directory is a subfolder of it). No hardcoded absolute paths.
- **Mode/ticker** — `--mode demo --ticker DEMO` (synthetic self-check) or
  `--mode live --ticker <TICKER>`.
- **`SEC_USER_AGENT`** (live, required) — a descriptive app name + real contact email;
  never expose it in generated reports.
- **`RESTRICTED_IN_SHORT_TERM_USD`** (optional) — a note-verified restricted-investment
  amount for the bridge "reconciled" case; when unset the bridge reports a
  conservative-to-upper range.
- **Peer mapping** (optional, config) — `autoval/peers.py` maps an industry to candidate
  peer groups; other tickers default to no peers (see Failure handling).

## Invocation

```bash
# offline self-check (synthetic; never mix with live)
.venv/bin/python run_analysis.py --mode demo --ticker DEMO --output outputs/demo_run

# live ticker
export SEC_USER_AGENT="AutoValStudentResearch you@example.edu"
.venv/bin/python run_analysis.py --mode live --ticker TICKER --output outputs/<ticker>_live

# verify + tests
.venv/bin/python verify_output.py --analysis outputs/<ticker>_live/analysis.json
.venv/bin/python -m unittest discover -s tests -v
```

## Outputs (per run)

`analysis.json`, `summary.md`, `technical.csv`, `forecast.csv` (driver runs),
`peer_comparison.csv` + `relative_valuation.json` (when peers configured),
`verification.json`, `DATA_AUDIT.md` / `RECORD.md` (when written).

## Dependencies

`requirements.txt` (streamlit, pandas, numpy, requests, yfinance, pytest). Two soft
dependencies are also used and degrade gracefully if absent: `beautifulsoup4` (Damodaran
ERP parsing) and a market-data connection for prices/beta. Python 3.11+.

## Failure handling (per component — never blocks the core)

- **WACC inputs unavailable** (e.g. FRED/Damodaran down) → WACC marked unavailable; the
  run still shows price/financials/technical, and intrinsic values use the **illustrative**
  WACC with an explicit label (not presented as company-specific).
- **Peer group unavailable** (industry not configured, or <3 valid peers) → relative
  valuation is marked unavailable/limited; the **DCF/WACC/forecast result still succeeds**.
- **Missing SEC tags / stale data / provider blocks** → the run stops with an informative
  error rather than substituting synthetic figures.

## Verification

- `verify_output.py` recomputes DCF independently (Decimal) to within $0.01/share.
- Regression suite: **91 tests** (`unittest discover -s tests`).
- Open the actual files; a bare "done" message does not count as evidence.

## Limitations

- U.S. nonfinancial SEC filers only (banks/insurers need different methods).
- Driver assumptions are trailing-3-year rules + a 21% normalized-tax baseline — not
  forward guidance.
- Small peer samples make quartiles coarse; P/E is more reliable than EV/EBITDA (debt and
  D&A XBRL tags vary by issuer).
- Market prices are delayed closes, never real-time. No trading or investment advice.

## Cross-company tag handling

XBRL tag names vary by issuer. The extractors support alternative standard tags and fall
back (never summing overlapping tags): CapEx `PaymentsToAcquirePropertyPlantAndEquipment`
→ `PaymentsToAcquireProductiveAssets`; long-term debt `LongTermDebtNoncurrent` →
`LongTermDebtAndCapitalLeaseObligations` → `LongTermDebt`; current debt `LongTermDebtCurrent`
→ `LongTermDebtAndCapitalLeaseObligationsCurrent`; short-term `ShortTermBorrowings` →
`CommercialPaper`. Lease-inclusive debt tags already contain finance leases, which are
therefore **not** added again to enterprise value.

## Reuse evidence

After import, run a fresh ticker + fresh output folder in a new conversation, record the
exact invocation/versions, saved files, independent check and a screenshot; attribute
self-reproduction honestly. A worked example is `outputs/hd_fresh_skill/` (Home Depot, a
non-software industry whose capex/debt tags differ from MSFT — see its `RECORD.md`).
Refer to `references/methodology.md`.
