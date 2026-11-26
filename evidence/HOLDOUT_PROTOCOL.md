# Holdout Protocol — Phase 2F

## Objective

Measure the contribution of the AI Financial Reconciliation Agent on **previously unseen**
companies, frozen before evaluation to prevent tuning.

## Frozen evaluation version

- Branch: `ai-financial-reconciliation`
- Evaluation commit: `3723bbe` (HEAD before Phase 2F), plus the share-unit-consistency
  refinement and the gross/net-debt metric guard committed in this phase **before** any
  holdout result was observed.
- Reporting cutoff: 2026-11-25 (SEC filings up to this date).

## Selection rule

Five U.S.-listed, nonfinancial operating companies, one per industry, that are:
1. **Not** in the 20 development companies (MSFT, AMZN, AAPL, HD, GOOGL, TSLA, NVDA, WMT,
   COST, KO, PG, MCD, NKE, XOM, CAT, UPS, JNJ, DIS, ORCL, AMD).
2. **Not** used as peer-group reference tickers to tune extraction rules.
3. U.S. GAAP SEC filers with consolidated cash-flow statements.

**Selected tickers (industry):**
1. PFE — Pfizer (pharmaceuticals)
2. INTC — Intel (semiconductors)
3. DE — Deere & Co (industrial machinery)
4. PEP — PepsiCo (beverages/food)
5. CSCO — Cisco (networking/IT)

## Evaluation criteria (fixed before execution)

Per company, record: financial-extraction accuracy; baseline extraction failures; recovered
failures; incorrect-correction acceptance; correct no-change decisions; full-valuation
availability; source-data verification; independent arithmetic verification; LLM calls,
tokens, latency and cost (where available). If no baseline failure occurs, the recovery rate
is reported as **not measurable** — no company is replaced to manufacture a failure.

## Method comparison (identical snapshots + LLM responses)

- **A** — deterministic extraction only (no AI).
- **B** — raw LLM reconciliation proposals, evaluated **offline only** (never applied).
- **C** — the same LLM proposals after AutoVal's deterministic validation + approval workflow.

Maximum **5 paid runtime LLM calls** (one per company). Successful investigations are not
repeated.

## Frozen rules

No new financial models, no market-price tuning, no modification of the production
implementation after observing holdout results. Failures are documented for future
development, not fixed during evaluation.
