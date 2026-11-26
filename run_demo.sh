#!/usr/bin/env bash
# Public demonstration launcher: enforces protected demo mode (no paid LLM, no runtime-config
# fallback) and runs the offline demo with in-app company switching.
set -euo pipefail
export AUTOVAL_PUBLIC_DEMO=1
export AUTOVAL_LLM_USE_RUNTIME_CONFIG=0
export AUTOVAL_FIXTURE_TICKER="${AUTOVAL_FIXTURE_TICKER:-MSFT}"
exec python -m streamlit run app.py --server.headless true "$@"
