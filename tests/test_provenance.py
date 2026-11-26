import unittest
from autoval.provenance import build_provenance, record


def _result():
    return {
        "ticker": "MSFT", "run_utc": "2026-11-25T00:00:00Z",
        "analysis": {
            "scenarios": {"base": {"intrinsic_per_share_usd": 100.0}},
            "forecast": {"base": {"drivers": {"revenue_growth": 0.10, "operating_margin": 0.20,
                                                "capex_ratio": 0.10, "da_ratio": 0.05,
                                                "nwc_ratio": 0.15, "normalized_tax_rate": 0.21}}},
            "ttm": {"asof": "2026-09-30", "revenue": 346_445e6},
        },
        "provenance": {"financials": {
            "cik": 789019, "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
            "units": "USD",
            "shares": {"value": 7.453e9, "end": "2026-09-30", "tag": "EntityCommonStockSharesOutstanding", "filed": "2026-10-28"},
            "cash": {"value": 78.0e9, "end": "2026-09-30", "tag": "CashAndCashEquivalentsAtCarryingValue", "filed": "2026-10-28"},
            "long_debt": {"value": 31.09e9, "end": "2026-09-30", "tag": "LongTermDebtNoncurrent", "filed": "2026-10-28"},
            "finance_lease": {"value": 70.97e9, "end": "2026-09-30", "tag": "FinanceLeaseLiability", "filed": "2026-10-28"},
            "debt_reconciliation": {"reference_date": "2026-09-30", "net_debt": 86.17e9},
        }},
    }


class ProvenanceTests(unittest.TestCase):
    def test_reported_facts_classified(self):
        recs = build_provenance(_result())
        reported = [r for r in recs if r["kind"] == "reported"]
        self.assertGreaterEqual(len(reported), 4)
        self.assertTrue(all(r["verification_status"] == "companyfacts" for r in reported))

    def test_derived_and_estimated_distinguished(self):
        recs = build_provenance(_result())
        kinds = {r["metric"]: r["kind"] for r in recs}
        self.assertEqual(kinds.get("net_debt"), "derived")
        self.assertEqual(kinds.get("revenue_ttm"), "derived")
        self.assertEqual(kinds.get("revenue_growth"), "estimated")

    def test_no_auto_independent_verification(self):
        recs = build_provenance(_result())
        self.assertFalse(any(r["verification_status"] == "independent" for r in recs),
                         "companyfacts agreement must not be auto-promoted to independent")

    def test_record_has_required_fields(self):
        r = record("id", "T", "s", "m", "u", "a", "n", "t", "c", "ps", "pe", "f", "U",
                   None, 1.0, "formula", 1.0, "derived", "expl", "derived")
        for k in ("evidence_id", "metric", "source_url", "accession", "xbrl_tag",
                  "verification_status", "kind", "dependencies"):
            self.assertIn(k, r)

    def test_missing_evidence_graceful(self):
        # a legacy/minimal result with no provenance must not raise
        recs = build_provenance({"ticker": "X", "run_utc": "t", "analysis": {}})
        self.assertEqual(recs, [])

    def test_snapshot_isolation(self):
        r1 = build_provenance(_result())
        r2 = _result(); r2["run_utc"] = "2026-11-26T00:00:00Z"
        r2 = build_provenance(r2)
        self.assertNotEqual(r1[0]["snapshot_id"], r2[0]["snapshot_id"])
        # evidence_id is stable across snapshots (same company.metric), snapshot_id differs
        self.assertEqual(r1[0]["evidence_id"], r2[0]["evidence_id"])


if __name__ == "__main__":
    unittest.main()
