# Reproducibility

## Requirements
- macOS/Linux, Python 3.11+.
- `pip install -r requirements.txt`.
- Live SEC/market access requires a `SEC_USER_AGENT` (`.env`); deterministic tests run without it.

## Run the full test suite
```bash
cd /Users/yumin/Downloads/autoval-clean-1795437027
.venv/bin/python -m unittest discover -s tests
```
Result (release candidate): **200 tests OK**.

## Independent reference calculation
```bash
.venv/bin/python evidence/reference_calc.py MSFT   # writes evidence/financial_reconciliation.csv
```

## Independent DCF verification
```bash
.venv/bin/python verify_output.py --analysis outputs/<ticker>_live/analysis.json
```

## Website
```bash
.venv/bin/python -m streamlit run app.py
```

## Data provenance
- Live SEC: fresh retrieval (EDGAR companyfacts).
- Market price / WACC market inputs (beta, rf, ERP, equity value): dated saved snapshots
  when Yahoo Finance is unavailable — explicitly labeled, never presented as fresh.
- `evidence/financial_reconciliation.csv`: reconciled source vs AutoVal values.

## Sanitization
No credentials, real SEC contact emails, or restricted financial data are committed.
`.env`, `outputs/`, and caches are git-ignored.
