# AutoVal AI Pro

A ticker-only, automated U.S. equity-valuation research tool. Enter a stock ticker; the
pipeline retrieves SEC filings and market data, then produces a transparent, multi-method
valuation with source dates and assumptions kept visible. Built as a final project for a
"Finance with AI Agents" course.

> ⚠️ Educational research prototype. Prices are delayed (never real-time) and the results
> are **not** investment advice. No trading is performed.

## The finance problem

Estimating the intrinsic value of a public company is laborious: it requires pulling
financial statements, reconciling tags and periods, computing free cash flow, estimating a
cost of capital, and comparing against peers — usually by hand. AutoVal AI Pro automates
this from a single ticker while making every assumption, source date and limitation
explicit, so the result is reproducible and auditable rather than a black box.

## Target user & supported companies

- **User:** an investor or finance student who wants a reproducible, source-linked
  valuation without hand-entering financial statements or prices.
- **Supported companies:** U.S.-listed **nonfinancial** SEC filers (US GAAP). Banks and
  insurers are out of scope (they require DDM / excess-return / book-value methods rather
  than FCFF).

## Architecture

```
run_analysis.py          CLI entry point
verify_output.py         independent Decimal-based DCF re-check
app.py                   Streamlit dashboard
autoval/
  sec.py                 SEC XBRL extraction (annual + quarterly, alternative tags)
  forecast_data.py       driver inputs (revenue, margin, D&A, capex, NWC)
  forecast.py            five-year driver-based FCFF forecast
  finance.py             DCF + enterprise-to-equity bridge
  wacc.py / wacc_data.py company-specific WACC
  peers.py / relative.py / relative_data.py   P/E + EV/EBITDA relative valuation
  market.py / technical.py   prices + SMA/backtest
  pipeline.py            orchestration
tests/                   97 automated tests
skills/autoval-equity-research/   reusable WorkSwarm Skill
```

**WorkSwarm's role:** WorkSwarm hosts the reusable `autoval-equity-research` Skill, which
documents and executes the workflow (SEC retrieval → driver DCF → WACC → bridge → relative
valuation → technical → verification). All valuation arithmetic is deterministic Python;
the assistant orchestrates and documents but never computes the math itself.

## Installation (macOS)

```bash
cd AutoVal_AI_Starter
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Python 3.11+ is required (developed on 3.13.5). Dependencies (`requirements.txt`):
`streamlit`, `pandas`, `numpy`, `requests`, `yfinance`, `beautifulsoup4`, `pytest`.

## SEC contact configuration

Live SEC access requires a descriptive `User-Agent` with a real contact email (a fair-access
compliance requirement, **not** a financial input). Copy `.env.example` to `.env` and fill
in your own address:

```bash
cp .env.example .env
# edit .env:  SEC_USER_AGENT=AutoValStudentResearch your-school-email@example.edu
```

`.env` is git-ignored; never commit your real email.

## Run the analysis

```bash
# offline self-check (synthetic — never mixed with live)
python run_analysis.py --mode demo --ticker DEMO --output outputs/demo_run

# live ticker (loads SEC_USER_AGENT from .env)
set -a && . ./.env && set +a
python run_analysis.py --mode live --ticker TICKER --output outputs/<ticker>_live
```

Optional: `RESTRICTED_IN_SHORT_TERM_USD=<amount>` sets a note-verified restricted-investment
amount for the bridge's "reconciled" case (defaults to a conservative/upper range).

## Streamlit website

```bash
python -m streamlit run app.py
```

Open the printed URL (usually http://localhost:8501). The dashboard shows Valuation,
Forecast, Relative valuation, WACC, Technical, and Sources tabs.

## Verification & tests

```bash
python verify_output.py --analysis outputs/<ticker>_live/analysis.json
python -m unittest discover -s tests -v   # 97 tests
```

`verify_output.py` recomputes the DCF independently with `Decimal` arithmetic to within
$0.01/share.

## Examples

- **MSFT (full pipeline, with peers):** `outputs/workswarm_msft_v8/` — driver DCF, company
  WACC (~10%), investment bridge, and P/E / EV/EBITDA peer comparison.
- **HD (fresh-case Skill test):** `outputs/hd_fresh_skill/` — a different-industry
  reproduction; see that folder's `RECORD.md`. (HD has no configured peer group, so the
  relative valuation is correctly reported as unavailable.)

## Known limitations & data-source restrictions

- **Nonfinancial US SEC filers only.** Banks/insurers need different methods.
- **XBRL tags vary by issuer.** The extractors support alternative tags for capex
  (`PaymentsToAcquireProductiveAssets`) and debt (`LongTermDebtAndCapitalLeaseObligations`,
  `CommercialPaper`), but unusual issuers may still hit a "missing tag" stop.
- **Driver assumptions** are trailing-3-year rules plus a 21% normalized-tax baseline — not
  forward guidance.
- **Small peer samples** make quartiles coarse; P/E is more reliable than EV/EBITDA.
- **Market data licensing:** yfinance/Yahoo prices are for personal/research use only. Do
  not publicly redistribute raw prices or deploy a public app without a licensed provider.
- Prices are delayed closes, never real-time. No trading or investment advice.

## Attribution & license

Developed with substantial AI coding assistance, then independently tested and audited
(the FCFF reconciliation, WACC and EV/EBITDA corrections in this repo are the result of
that audit). Any external financial/market data remains subject to its provider's terms;
the MIT license (see `LICENSE`) covers only this software.

- openJiuwen (WorkSwarm): https://github.com/openJiuwen-ai/jiuwenswarm
- SEC EDGAR: https://www.sec.gov/developer
- yfinance: https://github.com/ranaroussi/yfinance
- Damodaran (implied ERP): https://pages.stern.nyu.edu/~adamodar/
