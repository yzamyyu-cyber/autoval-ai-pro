# Publication Handover (Phase 8.1)

Branch: `release-v1` · Checkpoint `4e7c5c7`.

## Release readiness: **CONDITIONAL GO**

Release is gated on two non-blocking items (documented, not release-blocking):
1. Excel engine recalculation was **NOT EXECUTED** (no LibreOffice in this environment) —
   provide the manual Microsoft Excel verification procedure below before presenting the
   workbook as "recalculated".
2. ORCL / WMT / TSLA remain materially limited (negative bear/equity) — reported honestly,
   never tuned.

All security gates PASS (no credentials, no PII, demo cannot invoke paid LLM).

## Mac launch commands

```bash
cd /path/to/autoval-ai-pro
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# Offline guided demo (deterministic, no network, no credentials):
AUTOVAL_FIXTURE_TICKER=MSFT streamlit run app.py
#   (also AMZN / AAPL / HD / GOOGL / TSLA / NVDA)

# Full workspace (live analysis requires SEC_USER_AGENT):
streamlit run app.py
```

## GitHub publication commands (do NOT run without explicit authorization)

```bash
git checkout release-v1                      # sanitized release branch
git remote add origin <your-repo-url>
git push -u origin release-v1
```

> This repository has never been pushed or merged. Publication is blocked pending your
> explicit authorization.

## Website deployment (local / Streamlit)

```bash
streamlit run app.py --server.headless true --server.port 8501
```

Deployment notes: set `SEC_USER_AGENT` and (optionally) `AUTOVAL_LLM_*` as **server-side
environment variables** only — never in the repo. The offline demo runs with no credentials.

## Rollback procedure

```bash
git checkout 4e7c5c7     # restore the pre-publication checkpoint
# or: git revert <bad-commit>
```

Feature branches are atomic; the prior commit is always recoverable.

## Manual Excel verification procedure (for NOT-EXECUTED recalc)

1. Open `evidence/exports/MSFT_valuation.xlsx` in Microsoft Excel / LibreOffice.
2. On **FCFF Forecast**, select the first `FCFF` cell (`G2`) — it must be a formula
   `=C2+D2-E2-F2`, not a constant.
3. Change a **blue** (editable) assumption cell, e.g. **Forecast Assumptions → CapEx/revenue**
   from `31.8%` to `35.0%`, and press Enter.
4. Confirm the dependent FCFF and, via the DCF sheets, the intrinsic value update (they
   should **decrease**, matching the Python engine's direction).
5. Undo (`Ctrl+Z`) or reopen to restore the original file.

If any derived cell is a hardcoded number or fails to update, the workbook is invalid.
