# Application Acceptance Matrix

## Automated application tests (Streamlit AppTest, deterministic)

| Area | Coverage | Status |
|---|---|---|
| All six research tabs render (Overview, Scenario Lab, Multi-stage DCF, Market Expectations, Financials, Evidence & Exports) | DEMO | ✅ `tests/test_app_integration.py` |
| Basis selector (Annual/TTM) | DEMO | ✅ present |
| Scenario slider + reset | DEMO | ✅ `test_app.py` |
| Compare Companies (bundled + saved files) | DEMO/DEMO2 | ✅ `test_app.py` |
| Failed live retrieval keeps last report + flags stale ticker | mocked | ✅ `test_app.py` |
| Mature ROIC crash (missing roic_sensitivity) | mocked | ✅ `test_app_integration.py` |
| Negative modeled equity → "N/A" | mocked | ✅ `test_app_integration.py` |
| Fiscal-date not overwritten | mocked | ✅ `test_app_integration.py` + `test_basis.py` |
| Incorrect peer sample counts | unit | ✅ `test_relative.py` |
| Market-provider retry/failure | unit | ✅ `test_market.py` |

## Not covered by automated tests
- **Live 7-ticker run** (MSFT/AMZN/AAPL/HD/GOOGL/TSLA/NVDA): requires SEC_USER_AGENT + Yahoo Finance; run manually.
- **Browser (visual) rendering**: not automated — see `BROWSER_TEST_REPORT.md`.

## Test totals
- Full suite: **212 passing** (`python -m unittest discover -s tests`).
- Independent reference (synthetic): `python -m unittest tests.test_reference_calc` (5 tests).
