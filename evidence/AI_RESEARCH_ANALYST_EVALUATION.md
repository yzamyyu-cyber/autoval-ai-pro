# AI Research Analyst — Evaluation (Phase 3A)

Branch: `ai-research-analyst` (forked from `d417059`).

## Holdout preservation & safety (Task 1)

The frozen five-company holdout (PFE/INTC/DE/PEP/CSCO) is preserved unchanged. A targeted
regression test now ensures a **validated debt component** (e.g. short-term borrowings, the
CSCO case) **cannot be applied as a complete total/net debt figure**
(`_classify_metric` → `"component"`, `apply_correction` → `unsupported_component`,
`apply_approved` → `rejected`).

## AI Research Analyst (Tasks 2–3)

New read-only module `autoval/research.py`:
- `render_tables(result)` — renders all financial tables **deterministically from Python**
  (DCF scenarios, multi-stage, drivers, WACC, comparables, evidence records). The LLM never
  reproduces numbers.
- `build_report(result, chat_fn)` — prompts the LLM to write the narrative sections only,
  distinguishing REPORTED / DERIVED / ASSUMED / INTERPRETATION.
- `validate_report(report, result)` — rejects unknown evidence IDs, ticker mismatches, and an
  unsupported headline price when the valuation is unavailable/low-confidence.

A unit bug found and fixed: `upside_vs_price_pct` is already a percentage, so it is formatted
as `+x.x%` (not re-scaled by 100).

## Website (Task 4)

New **"AI Research Analyst"** tab with: generate button, cached reports (company × snapshot ×
basis), evidence-grounded sections, deterministic tables, clickable SEC link, Markdown
download, and graceful failure when the LLM is unconfigured. No LLM call on rerun.

## Acceptance cases (Task 5) — 3 LLM calls

| Case | Quality | Validation | Report |
|---|---|---|---|
| MSFT (standard) | available | validated | `research_report_msft.md` |
| WMT (accounting correction) | unsuitable | validated | `research_report_wmt.md` |
| ORCL (unavailable headline) | unavailable | validated | `research_report_orcl.md` |

All three reports cite real evidence IDs (`[MSFT.cash_and_equivalents]`, `[ORCL.net_debt]`,
…), distinguish fact/derivation/assumption/interpretation, and the ORCL report does not
present a headline valuation (negative-equity → unavailable).

## Tests

`tests/test_research.py` (8 tests, mocked): fabricated evidence IDs, wrong company, API
failure, unsupported headline suppression, tables-from-Python, AppTest tab render, and the
debt-component regression. Full suite: **319 passed, 32 subtests passed**.

## API usage

3 LLM calls (MSFT/WMT/ORCL); no token/cost metering exposed by the endpoint. All development
and testing used mocked responses first.

## Limitations

- Fixture snapshots used for deterministic tests carry balance-sheet evidence only (no income
  statement), so the MSFT narrative correctly notes "no reported income-statement records".
- Reports require a configured LLM; without it the tab degrades gracefully.

No SOTP/Monte Carlo/new forecasting; no API keys exposed; no push/merge.

---

# Phase 3B — Research Quality and Evidence Acceptance

Checkpoint: `bb7d640` · Branch: `ai-research-analyst`

## Research context (Task 1)

`render_tables` + `data_context` now include: annual + TTM revenue, operating income/margins,
historical D&A, CapEx, FCFF trends, debt/cash/shares, WACC + forecast drivers, five-year and
multi-stage DCF, sensitivity grid and comparable valuation. Every metric carries a
definition, period, units and evidence reference.

## Claim validation (Task 2)

`validate_report` now requires **structured financial claims** (`{evidence_id, metric, value,
period_end}`) bound to their actual supporting values. It validates company, snapshot,
period, metric, units and numerical value — a valid citation ID with the wrong value or
period is rejected. Narrative figures are still rendered deterministically, not reproduced by
the LLM.

## Snapshot & cache integrity (Task 3)

Cache key now includes snapshot identity, valuation basis, market-data mode, prompt version
and model version. A changed snapshot/assumption invalidates the cached report. No automatic
LLM call on ticker switch / tab navigation / rerun.

## Acceptance (Task 4) — 2 LLM calls

| Case | Quality | Base intrinsic | Base equity | Validation | Claims |
|---|---|---:|---:|---|---:|
| MSFT (comprehensive) | available | $163.81 | $1,220.9B | validated | 6 |
| WMT (corrected) | unsuitable | **$17.51** | **$140.5B** | validated | 5 |

WMT uses the **corrected snapshot** (positive base equity $140.5B / $17.51 per share), not
the obsolete negative-equity analysis. Its "unsuitable" quality reflects a thin FCFF margin
and a negative bear scenario (a legitimate model limitation), not an obsolete base case.
ORCL report reused for the unavailable-valuation safeguard (headline suppressed).

## Verification (Task 5)

Regression tests added: incorrect value on a valid citation, stale snapshot, percentage
scaling (no ×100 double-scaling), missing evidence, unsupported headline. Full suite:
**323 passed, 32 subtests passed**. AppTest renders the research tab; Playwright (research UI)
reports 0 page errors.

## API usage

2 new LLM calls (MSFT + WMT). No token/cost metering exposed by the endpoint.
