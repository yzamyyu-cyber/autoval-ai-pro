# Automatic Comparable-Company Selection (Phase 4)

Branch: `automatic-peer-selection` (forked from `60a965c`). Zero LLM calls.

## Automatic peer discovery (Task 1)

`autoval/peers.py` now provides:
- `get_company_sic(ticker, ua)` — SEC SIC code + description from the submissions header.
- `discover_peers(ticker, ua, candidate_universe)` — returns `{method, industry, sic,
  sic_description, groups, excluded}`:
  - **curated** when the ticker is mapped (preserves stronger economic comparability);
  - **sic** when unmapped (same-SIC discovery over a candidate universe);
  - **sic_unavailable** when no SIC/user-agent is available.
- Exclusion reasons recorded: the target itself, duplicate share classes (GOOG/GOOGL,
  BRK.A/BRK.B), financial-company SIC ranges (6000–6799), and unavailable SIC.

## Financial screening (Task 2)

`screen_peers` retains independent P/E and EV/EBITDA eligibility. A missing target market
price does **not** suppress a valid peer-implied valuation (implied value uses peer multiples
+ target fundamentals). Headline medians require ≥3 eligible peers per metric; financial
company models are excluded; peer selection never uses market-price proximity.

## Website (Task 3)

`render_peers` now shows the peer-selection method (curated vs SIC), industry/SIC, exclusion
rationale, and the per-group P/E and EV/EBITDA medians + implied values.

## Acceptance (Task 4)

Validation matrix `evidence/peer_selection_matrix.json`:

| Ticker | Method | SIC | Groups |
|---|---|---|---|
| MSFT | curated | 7372 (software) | core_software, supplemental_software, cloud_platform |
| AMZN | curated | 5961 (retail) | retail, ecommerce, cloud_platform, advertising |
| AAPL | curated | 3571 | consumer_technology |
| WMT / NKE / ORCL | curated | — | per industry |

Amazon's **retail**, **cloud** and **advertising** peers remain economically distinct (not
blended). Unmapped-company SIC discovery is covered by
`tests/test_peer_selection.py::test_unmapped_sic_discovery` (fixture).

## Regression tests (Task 4)

`tests/test_peer_selection.py` (8 tests): curated groups, Amazon distinct groups, financial-SIC
exclusion, duplicate share classes, unmapped SIC discovery (mocked), insufficient peers,
invalid peer data, and peer-implied survives missing target price.

Full suite: **331 passed, 32 subtests passed**.

## API usage

0 LLM calls; network used only for SIC lookups and previously-cached SEC facts.

## Limitations

- SIC-based discovery over a large universe is bounded by the candidate universe (network
  cost); curated groups remain the primary source where mapped.
- Conglomerate peers (e.g. AMZN) are reported in separate economic groups, not blended.
