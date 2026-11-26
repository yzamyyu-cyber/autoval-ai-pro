# Three-Minute Demonstration Script

Launch the offline demo (no credentials, no network):

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
AUTOVAL_FIXTURE_TICKER=MSFT streamlit run app.py
```

| Time | Action | Highlight |
|---|---|---|
| 0:00 | Open the **Overview** tab | Valuation-quality banner, three DCF cards, source dates, independent check |
| 0:20 | **Multi-stage DCF** tab | Five-year vs multi-stage comparison (MSFT base $163.81 vs $317.70) |
| 0:40 | **Financials** tab → "Enterprise-to-equity bridge" | Debt/cash/leases → equity, transparent bridge |
| 1:00 | Switch ticker to **AMZN** | Automatic peer groups (retail / cloud / advertising kept distinct) |
| 1:20 | **Evidence & Exports** tab | Financial evidence centre, Excel + PDF downloads |
| 1:45 | **AI Research Analyst** tab | Cached, evidence-grounded research report (facts vs derivation vs interpretation) |
| 2:15 | **AI Financial Reconciliation** (in Evidence) | Detected issues + validated proposal + approval controls |
| 2:40 | **Walmart reconciliation** (cached evidence) | $35.2B → $45.7B net-debt correction; D&A 0.13% → 1.93% recovery |
| 2:55 | **Multi-stage DCF** (Amazon) | Horizon-aware CapEx: temporary investment fades, ROIC-consistent terminal |

Key talking points: deterministic valuation engine (no black box), accounting-aware D&A resolver,
source-linked provenance, automatic peer screening, and read-only AI agents that are
evidence-grounded and never tune toward market price.
