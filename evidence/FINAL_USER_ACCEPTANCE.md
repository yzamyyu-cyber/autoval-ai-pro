# Final User Acceptance (Phase 10D)

Branch `release-v1` · Standalone package `autoval-public-release`.

## PASS

| Requirement | Result |
|---|---|
| Public-demo LLM prohibition enforced at the entrypoint (st.secrets), not only `run_demo.sh` | **PASS** (`main()` reads `AUTOVAL_PUBLIC_DEMO` from secrets → forces backend guard) |
| Backend paid-LLM prohibition with mocked credentials | **PASS** (`test_public_demo_blocks_paid_llm_even_with_credentials`) |
| Private grounded Q&A claims validation (mocked) | **PASS** (`tests/test_research.py`: valid/fabricated/provider-failure) |
| Research cache invalidation on assumption/basis change | **PASS** (cache-key + `validate_research_cache_match` tests) |
| Excel formula dependencies (FCFF, WACC, multi-stage, sensitivity) | **PASS** (static formula presence + numerical-parity test) |
| Full automated suite | **PASS — 356 passed, 32 subtests** |

## NOT EXECUTED (requires live browser/tools not automatable here)

| Requirement | Status |
|---|---|
| Live KO/DIS ticker search + full workflow (SEC + market) | NOT EXECUTED (network/market flakiness) |
| Peer inclusion/exclusion recalc + Market Data period selectors (genuine OHLCV) | NOT EXECUTED (no genuine OHLCV in fixtures) |
| Excel/PDF download through the browser + engine recalculation vs Python | NOT EXECUTED (no LibreOffice/Excel automation) |
| PDF page-by-page visual inspection | NOT EXECUTED (no rasterizer) |

## FAIL

None. (Prior defects — MSFT price-history mismatch, ticker search, Excel formulas — were fixed in 10A/10B.)

## Remaining limitations

- Private free-text Q&A requires authorized server-side `AUTOVAL_LLM_*` (not exercised here).
- ORCL/WMT/TSLA remain materially limited (negative bear/equity) — reported honestly.
- Candidate universe for SIC peer discovery is bounded; curated groups remain primary.

## Files

- Excel/PDF: `evidence/exports/{MSFT,AMZN,ORCL}_valuation.{xlsx,pdf}`
- Manual verification cells documented in `evidence/PROFESSIONAL_EXPORT_ACCEPTANCE.md`.