# Browser Test Report

## Status: EXECUTED (real Playwright + Chromium)

Dependencies installed into the project venv and pinned in `requirements-dev.txt`:
- `playwright==1.65.2`
- `pytest-playwright==0.10.0`
- Chromium (headless shell 159.0.8154.6) via `playwright install chromium`.

## Execution evidence (`evidence/browser_test.py`)

The actual Streamlit server was launched and driven with Playwright Chromium:

| Check | Result |
|---|---|
| Page title | `AutoVal AI Pro` |
| Overview tabs render | ✅ |
| Compare Companies table renders | ✅ |
| Mobile (390px) layout | ✅ |
| Unhandled page errors | **0** |

Genuine screenshots captured:
- `evidence/screenshot_overview.png` (desktop Overview)
- `evidence/screenshot_compare.png` (Compare Companies)
- `evidence/screenshot_mobile.png` (390px mobile)

```bash
.venv/bin/python evidence/browser_test.py
```

## Remaining (honest)
- Browser test exercises the **offline demo** (deterministic, no live providers). The
  seven live tickers require SEC contact + Yahoo Finance (yfinance was down); their
  live browser validation is not yet executed.
- Desktop/mobile **visual overflow** was not formally asserted (screenshots captured, not
  pixel-diffed); the layout rendered without console/page errors at both widths.
