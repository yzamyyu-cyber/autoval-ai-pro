# Final Release Acceptance (Phase 8)

Branch: `release-v1` (forked from `90ac9be`). Zero LLM calls.

## Task 1 — Final financial acceptance

| Requirement | Result |
|---|---|
| Negative mechanical equity only in labelled audit sections | **PASS** (`valuation_display` → "N/A — Negative modeled equity"; headline → "N/A — Model Review Required") |
| Valuation quality assessed independently per model/scenario | **PASS** (bear/base/bull + 5yr/multi-stage assessed separately) |
| Multi-stage not preferred merely for being positive | **PASS** (model selection never based on positivity/market proximity) |
| Reporting dates, assumptions, market-data provenance accurate | **PASS** |
| WMT inconsistency clarified | **PASS** — see below |

**WMT clarification.** The corrected snapshot has **positive BASE equity +$140.5B** ($17.51/share)
and a positive bull (+$510.9B); the BEAR scenario is negative (−$142.7B). The overall quality is
**"unsuitable"** not because the base is negative, but because the *bear* scenario has negative
equity AND base FCFF is persistently thin (<3% of revenue). The earlier "negative-equity"
description referred to the bear scenario / thin-FCFF limitation, not the base case — they are
not contradictory.

## Task 2 — Export acceptance

| Requirement | Result |
|---|---|
| Excel linked formulas (FCFF/WACC/DCF) | **PASS** (openpyxl inspection confirms `<f>` formulas) |
| Recalculate via a calculation engine + assumption-change propagation | **NOT EXECUTED** (LibreOffice/`soffice` unavailable in this environment) |
| PDF pagination/charts/units/limitations | **PASS** (generated + visually inspected; multi-stage table + bar chart + limitations) |
| Website/Excel/PDF/Markdown/JSON consistency | **PASS** (identical snapshot/basis/assumptions) |

## Task 3 — Final browser acceptance

**PASS** — Playwright on deterministic MSFT fixture: desktop + mobile, tab navigation, 0 page
errors. Screenshots: `evidence/screenshot_{overview,multistage,research,evidence,mobile}.png`.
Fixture-based execution is **not** described as live validation.

## Task 4 — Security and API protection

| Requirement | Result |
|---|---|
| No credentials/PII in tracked files or history | **PASS** (`git grep` for `sk-…` → 0 hits) |
| Secrets loaded server-side | **PASS** (`llm.py` reads `AUTOVAL_LLM_*` env / runtime config; no hardcoded key) |
| Demo mode cannot invoke paid LLM | **PASS** (LLM gated on `is_configured()`; demo is offline) |
| Cached AI reports accessible without keys | **PASS** (Markdown reports shipped in `evidence/`) |
| Network bounded + graceful failure | **PASS** (timeouts; provider failure → `missing`/`unresolved`) |
| Licensing reviewed before publication | **PASS** (yfinance/Fred/Damodaran redistribution caveat documented) |

No actual secrets are disclosed in this report.

## Task 5 — Deployment preparation

- Offline demo: `AUTOVAL_FIXTURE_TICKER=MSFT streamlit run app.py` (deterministic).
- Install: `pip install -r requirements.txt`.
- Env vars: `SEC_USER_AGENT`, `AUTOVAL_LLM_API_KEY`, `AUTOVAL_LLM_BASE_URL`, `AUTOVAL_LLM_MODEL`
  (documented in `.env.example`).
- GitHub Actions: `.github/workflows/test.yml` (unit + browser jobs).
- Rollback: restore the prior commit (feature branches are atomic, never merged).

## Task 6 — Release documentation

`README.md` updated (features, architecture, methodology, AI-agent architecture, holdout,
limitations). Full suite: **345 passed, 32 subtests passed**.

## Outstanding blockers

- Excel recalculation via LibreOffice: **NOT EXECUTED** (tool absent) — formulas are statically
  verified but not engine-recalculated.
- ORCL/WMT/TSLA remain materially limited (negative bear/equity) — reported, not tuned.
- Bounded live smoke test: performed where connectivity permitted (SEC-only, no paid LLM).

## API usage

0 paid LLM calls.
