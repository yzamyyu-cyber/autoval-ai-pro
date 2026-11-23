# AutoVal AI Pro

A ticker-only, automated U.S. equity-valuation research tool. Enter a stock ticker; the
pipeline retrieves SEC filings and market data, then produces a transparent, multi-method
valuation with source dates and assumptions kept visible. Built as a final project for a
"Finance with AI Agents" course.

> ⚠️ Educational research prototype. Prices are delayed (never real-time) and the results
> are **not** investment advice. No trading is performed.

## Run the research workspace

```bash
cd autoval-ai-pro
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, use `.venv\Scripts\activate` in Command Prompt to activate the environment.
Open the local URL printed by Streamlit (usually [localhost:8501](http://localhost:8501)).
The workspace opens to a synthetic company with a **$139.85** base DCF per share. This
example runs without network data or account configuration.

Run Streamlit in a terminal on the same computer as your browser and keep that terminal
open. If the browser cannot connect, check the terminal for the URL or startup error.

- **Overview** shows three DCF cases, the reference price, and the independent check.
- **Scenario Lab** lets you change WACC and terminal growth and see the result immediately.
  Try raising WACC from 10% to 11%. The synthetic estimate falls from **$139.85 to $122.62**
  per share with the forecast cash flows, net debt, and shares held fixed.
- **CapEx sensitivity** in Scenario Lab changes CapEx as a share of revenue while holding
  the other assumptions fixed. The offline manufacturing example falls from **$326.68**
  to **$231.27** per share when CapEx rises from 10% to 15% of revenue.
- **Market Expectations** uses reverse DCF to estimate the annual cash-flow growth that
  would match the reference or a hypothetical share price. Try **$145** and then **$170**
  in the bundled demo. Implied growth rises from **6.98% to 11.70%** under the same
  assumptions.
- **Financials** shows projected cash flow, the equity bridge, and cost of capital.
- **Evidence & Exports** shows each Decimal recomputation and downloads the Markdown
  report, underlying analysis JSON, and verification JSON.
- **Compare Companies** opens two bundled synthetic valuations and exports a CSV. Select
  **Saved analysis files** to compare any two AutoVal Analysis JSON exports.
  See [the comparison walkthrough](submission/COMPARE_COMPANIES.md).

For live analysis, select **Microsoft (MSFT)** or **Home Depot (HD)** to fill the ticker,
or type a ticker into the field. Enter your contact email in the browser and select
**Run live analysis**. The contact is held in the current session. **Load offline demo**
returns to the bundled example.

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
reverse_dcf.py           implied cash-flow growth from a saved analysis and share price
app.py                   Streamlit research workspace
autoval/
  sec.py                 SEC XBRL extraction (annual + quarterly, alternative tags)
  forecast_data.py       driver inputs (revenue, margin, D&A, capex, NWC)
  forecast.py            five-year driver-based FCFF forecast
  finance.py             DCF + enterprise-to-equity bridge
  reverse.py             reverse DCF with a forward-price check
  wacc.py / wacc_data.py company-specific WACC
  peers.py / relative.py / relative_data.py   P/E + EV/EBITDA relative valuation
  market.py / technical.py   prices + SMA/backtest
  pipeline.py            orchestration
tests/                   automated test suite
skills/autoval-equity-research/   reusable WorkSwarm Skill
```

**WorkSwarm's role:** WorkSwarm hosts the reusable `autoval-equity-research` Skill, which
documents and executes the workflow (SEC retrieval → driver DCF → WACC → bridge → relative
valuation → technical → verification). All valuation arithmetic is deterministic Python;
the assistant orchestrates and documents but never computes the math itself.

Python 3.11+ is required. See [requirements.txt](requirements.txt) for dependencies.

## SEC contact configuration for command-line use

Live SEC access requires a descriptive `User-Agent` with a real contact email (a fair-access
compliance requirement, **not** a financial input). Copy `.env.example` to `.env` and fill
in your own address:

```bash
cp .env.example .env
# Edit .env: SEC_USER_AGENT="AutoValStudentResearch your-school-email@example.edu"
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

## Reverse DCF from a saved analysis

```bash
python run_analysis.py --mode demo --ticker DEMO --output outputs/demo_run
python reverse_dcf.py --analysis outputs/demo_run/analysis.json --output outputs/demo_run/reverse_dcf.json
python reverse_dcf.py --analysis outputs/demo_run/analysis.json --price 170
```

The tool fixes year-one projected free cash flow to the firm (FCFF), shares, net debt,
WACC and terminal growth from the base DCF. It uses bisection to find a constant growth
rate for years 2 through the end of the forecast in the range −90% to +100%. It checks
that applying the implied growth reproduces the requested price within $0.01 per share.
The tool needs positive first-year FCFF and a valid WACC above terminal growth. It reports
out-of-range target prices. The growth result is conditional on these model assumptions.

## Verification & tests

```bash
python verify_output.py --analysis outputs/<ticker>_live/analysis.json
python -m unittest discover -s tests -v
```

`verify_output.py` recomputes each DCF with `Decimal` arithmetic and compares the result
against the $0.01/share tolerance. The suite uses synthetic or mocked inputs and runs
from a clean clone without historical output files, live data, or an SEC contact.

## Examples

- [Microsoft calculation walkthrough](submission/FINAL_FINANCIAL_VERIFICATION.md) records
  a dated run of the driver DCF, company WACC and equity bridge.
- [WorkSwarm evidence](submission/WORKSWARM_EVIDENCE.md) documents the Home Depot
  fresh-case run, including the SEC data issues and the verification result.
  Historical files under `outputs/` were local to the original runs.

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
- Product reference for interactive valuation workflows: https://www.stockoracle.com/features
