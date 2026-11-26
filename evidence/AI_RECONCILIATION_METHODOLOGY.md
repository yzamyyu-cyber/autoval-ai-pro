# AI Financial Reconciliation — Methodology

## Purpose

A reusable, AI-assisted workflow that investigates **missing, stale or conflicting financial
inputs** in the AutoVal SEC extraction and proposes **evidence-backed corrections**. The agent
is part of AutoVal (the `autoval/reconciliation` package), not an external assistant.

## Architecture

```
SEC companyfacts + filings  ──►  detect_issues(extraction)
                                      │
                                      ▼
                            retrieve (submissions, alternative tags, note text)
                                      │
                                      ▼
                            LLM investigate  ──►  structured proposal (JSON)
                                      │
                                      ▼
                            deterministic validate  ──►  validated / unresolved / rejected
                                      │
                                      ▼
                            human approve  ──►  apply to a SEPARATE snapshot
```

### Separation of responsibilities (deterministic safeguards)

1. **The LLM only proposes.** It never writes financial inputs, valuation formulas or
   production code. Its output is a JSON proposal conforming to `PROPOSAL_FIELDS`.
2. **The deterministic validator checks the proposal** against the raw companyfacts and the
   original extraction. Ten rules gate every proposal:
   - `company_identity` — ticker/company must match the extraction.
   - `reporting_period` — proposal period must equal the balance-sheet date.
   - `filing_lookahead` — filing date must not precede the reporting period.
   - `value_finite` — proposed value must be finite.
   - `units_scaling` — a 1e3/1e6/1e9 multiple of the original flags a unit/scaling warning.
   - `xbrl_tag_exists` — every cited tag must exist in companyfacts (or be a documented
     `Noncurrent+Current` combination).
   - `component_arithmetic` — the derivation formula, evaluated sandboxed (arithmetic only),
     must recompute the proposed value.
   - `debt_lease_double_count` — a finance-lease component must not be added to a
     lease-inclusive long-debt tag.
   - `restricted_cash` — a combined cash tag must not be claimed as unrestricted cash.
   - `source_evidence` — accession + sec.gov URL + note reference are required.
3. **Approval is explicit and separate.** A validated proposal stays `pending` until a human
   clicks Approve. Only an approved proposal is applied, and it is applied to a **deep copy**,
   never to the original analysis.
4. **All valuation arithmetic runs through the deterministic Python engine.** The agent never
   recomputes DCF/WACC; `apply_correction` only adjusts the single disputed input and recomputes
   the derived debt metrics deterministically.

## Untrusted data

Every retrieved SEC document (companyfacts, submissions index, filing HTML) is treated as
**untrusted data to inspect**, never as executable instructions. The LLM's JSON is parsed and
re-validated field-by-field; unknown keys are dropped; unsafe formula tokens are rejected.

## LLM configuration

The agent reads its model configuration from environment variables (`AUTOVAL_LLM_API_KEY`,
`AUTOVAL_LLM_BASE_URL`, `AUTOVAL_LLM_MODEL`), falling back to the JiuwenSwarm runtime config
(`~/.jiuwenswarm/config/config.yaml`, `models.defaults[0]`). **API keys are never hardcoded in
source, screenshots or exports.**

## Proposal schema

Every record carries: company, ticker, detected problem, original production value, proposed
value, financial definition, XBRL tags + component values, reporting period, filing date, SEC
accession, filing URL, statement/note reference, derivation formula, accounting explanation,
deterministic-validation result, remaining uncertainty, and approval status.

## Failure handling

- LLM/SEC unavailable → the proposal is marked `unresolved` (never silently resolved).
- Unsupported or unverifiable proposals remain `unresolved`.
- The website shows a graceful warning when the LLM API is not configured.
