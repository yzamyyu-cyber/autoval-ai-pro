"""Deterministic regression tests for the reconciliation agent (LLM mocked).

Covers proposal schema completeness, every deterministic safeguard, rejected proposals,
failed API requests, and the two carried-forward market-data requirements.
"""
import json
import unittest
from unittest.mock import patch

from autoval.reconciliation import (
    PROPOSAL_FIELDS, apply_correction, detect_issues, investigate, validate,
    apply_approved, recompute_wacc, regenerate_analysis,
)
from autoval.reconciliation.validate import _safe_eval


def _extraction(**overrides):
    base = {
        "ticker": "PG", "company": "The Procter & Gamble Company",
        "shares": 2_500_000_000,
        "net_debt": 45_000_000_000,
        "total_debt": 55_000_000_000,
        "debt_available": True,
        "cash_and_equivalents": 10_000_000_000,
        "balance_sheet_asof": "2026-06-30",
        "source": {
            "cash": {"tag": "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                     "value": 10_000_000_000, "end": "2026-06-30"},
            "long_debt": {"tag": "LongTermDebtNoncurrent", "value": 40_000_000_000},
            "finance_lease": {"tag": "FinanceLeaseLiability", "value": 0},
            "lease_assumptions": [], "lease_excluded": [],
            "disclosure_warnings": [],
            "excluded_debt_tags": [
                {"tag": "CommercialPaper", "status": "stale_nonzero",
                 "last_end": "2026-03-31", "last_value": 2_000_000_000},
            ],
            "debt_reconciliation": {
                "reference_date": "2026-06-30",
                "long_term_debt": 40_000_000_000,
                "current_portion_long_term_debt": 4_000_000_000,
                "short_term_borrowings": 0,
                "finance_lease": 0,
                "total_debt": 44_000_000_000,
                "cash_and_equivalents": 10_000_000_000,
                "net_debt": 34_000_000_000,
            },
        },
    }
    base.update(overrides)
    return base


def _facts(tags=None):
    us = {t: {"units": {"USD": []}} for t in (tags or [])}
    return {"facts": {"us-gaap": us, "dei": {}}}


def _proposal(**overrides):
    p = {
        "company": "The Procter & Gamble Company", "ticker": "PG",
        "detected_problem": "test issue",
        "original_production_value": 34_000_000_000,
        "proposed_financial_value": 32_000_000_000,
        "financial_definition": "net debt",
        "xbrl_tags": [
            {"tag": "LongTermDebtNoncurrent", "value": 40e9, "period_end": "2026-06-30",
             "filed": "2026-08-04", "form": "10-K"},
            {"tag": "LongTermDebtCurrent", "value": 2e9, "period_end": "2026-06-30",
             "filed": "2026-08-04", "form": "10-K"},
            {"tag": "CashAndCashEquivalentsAtCarryingValue", "value": 10e9,
             "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"},
        ],
        "reporting_period": "2026-06-30",
        "filing_date": "2026-08-04",
        "sec_accession": "0000080424-26-000048",
        "filing_url": "https://www.sec.gov/Archives/edgar/data/80424/000008042426000048/pg-20260630.htm",
        "statement_or_note_reference": "Note 4 — Debt",
        "derivation_formula": "LongTermDebtNoncurrent + LongTermDebtCurrent - CashAndCashEquivalentsAtCarryingValue",
        "accounting_explanation": "test",
        "remaining_uncertainty": "",
        "deterministic_validation": {"status": "pending", "checks": []},
        "approval_status": "pending",
        "category": "debt_component_stale_nonzero",
    }
    p.update(overrides)
    return p


class SchemaTests(unittest.TestCase):
    def test_proposal_schema_fields_present(self):
        p = _proposal()
        for f in PROPOSAL_FIELDS:
            self.assertIn(f, p)

    def test_detect_issues_flags_stale_nonzero(self):
        issues = detect_issues(_extraction())
        cats = [i["category"] for i in issues]
        self.assertIn("debt_component_stale_nonzero", cats)

    def test_detect_issues_flags_restricted_cash_scope(self):
        issues = detect_issues(_extraction())
        cats = [i["category"] for i in issues]
        self.assertIn("cash_restricted_scope", cats)


class SafeEvalTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(_safe_eval("A + B", {"A": 3, "B": 4}), 7.0)
        self.assertEqual(_safe_eval("A - B", {"A": 10, "B": 3}), 7.0)

    def test_rejects_unsafe(self):
        with self.assertRaises(ValueError):
            _safe_eval("__import__('os')", {})

    def test_tolerates_comma_numbers_and_trailing_expansion(self):
        # LLM often returns 'A + B = 10,000 + 20,000'; the symbolic LHS must evaluate.
        self.assertEqual(_safe_eval("A + B = 10,000 + 20,000", {"A": 10000, "B": 20000}), 30000.0)


class ValidationTests(unittest.TestCase):
    def test_valid_proposal_validates(self):
        facts = _facts(["LongTermDebtNoncurrent", "LongTermDebtCurrent",
                        "CashAndCashEquivalentsAtCarryingValue"])
        p = _proposal()
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "validated", r)

    def test_invalid_citation_rejected(self):
        facts = _facts(["LongTermDebtNoncurrent"])  # missing the other tags
        p = _proposal()
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("xbrl_tag_exists", r["hard_failures"])

    def test_incorrect_units_unresolved(self):
        facts = _facts(["LongTermDebtNoncurrent", "LongTermDebtCurrent",
                        "CashAndCashEquivalentsAtCarryingValue"])
        # proposed value 1000x the original, no components -> scaling warning only
        p = _proposal(proposed_financial_value=34_000_000_000_000, xbrl_tags=[])
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "unresolved")
        self.assertIn("units_scaling", r["soft_warnings"])

    def test_incompatible_period_rejected(self):
        facts = _facts(["LongTermDebtNoncurrent", "LongTermDebtCurrent",
                        "CashAndCashEquivalentsAtCarryingValue"])
        p = _proposal(reporting_period="2025-12-31")
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("reporting_period", r["hard_failures"])

    def test_overlapping_debt_rejected(self):
        facts = _facts(["LongTermDebtAndCapitalLeaseObligations", "FinanceLeaseLiability"])
        ext = _extraction()
        ext["source"]["long_debt"]["tag"] = "LongTermDebtAndCapitalLeaseObligations"
        p = _proposal(
            derivation_formula="LongTermDebtAndCapitalLeaseObligations + FinanceLeaseLiability",
            xbrl_tags=[
                {"tag": "LongTermDebtAndCapitalLeaseObligations", "value": 40e9,
                 "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"},
                {"tag": "FinanceLeaseLiability", "value": 5e9, "period_end": "2026-06-30",
                 "filed": "2026-08-04", "form": "10-K"},
            ])
        r = validate(p, ext, facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("debt_lease_double_count", r["hard_failures"])

    def test_lease_listed_but_not_added_is_not_double_count(self):
        # Control case: lease component listed for transparency but NOT in the formula.
        facts = _facts(["LongTermDebtAndCapitalLeaseObligations", "FinanceLeaseLiability",
                        "DebtCurrent"])
        ext = _extraction()
        ext["source"]["long_debt"]["tag"] = "LongTermDebtAndCapitalLeaseObligations"
        p = _proposal(
            derivation_formula="LongTermDebtAndCapitalLeaseObligations + DebtCurrent",
            proposed_financial_value=40_957_000_000,
            xbrl_tags=[
                {"tag": "LongTermDebtAndCapitalLeaseObligations", "value": 40e9,
                 "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"},
                {"tag": "DebtCurrent", "value": 957e6,
                 "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"},
                {"tag": "FinanceLeaseLiability", "value": 1467e6,
                 "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"},
            ])
        r = validate(p, ext, facts)
        self.assertEqual(r["status"], "validated", r)

    def test_missing_source_evidence_rejected(self):
        facts = _facts(["LongTermDebtNoncurrent", "LongTermDebtCurrent",
                        "CashAndCashEquivalentsAtCarryingValue"])
        p = _proposal(sec_accession="", filing_url="", statement_or_note_reference="")
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("source_evidence", r["hard_failures"])


class AgentTests(unittest.TestCase):
    def _run(self, extraction, chat_text):
        with patch("autoval.reconciliation.agent.retrieve.company_facts") as cf, \
             patch("autoval.reconciliation.agent.retrieve.latest_periodic", return_value=None):
            cf.return_value = (80424, "PG", _facts(["LongTermDebtNoncurrent", "LongTermDebtCurrent",
                                                    "CashAndCashEquivalentsAtCarryingValue"]))
            return investigate(extraction, "test@example.com",
                               chat_fn=lambda messages: chat_text)

    def test_llm_failure_stays_unresolved(self):
        def boom(messages):
            raise RuntimeError("LLM down")
        with patch("autoval.reconciliation.agent.retrieve.company_facts") as cf:
            cf.return_value = (80424, "PG", _facts(["LongTermDebtNoncurrent"]))
            p = investigate(_extraction(), "test@example.com", chat_fn=boom)
        self.assertEqual(p["approval_status"], "unresolved")
        self.assertIn("error", p["deterministic_validation"])

    def test_rejected_proposal_marked_rejected(self):
        # LLM returns a proposal citing a tag that is not in facts -> rejected
        bad = json.dumps(_proposal(xbrl_tags=[{"tag": "NotARealTag", "value": 1}]))
        p = self._run(_extraction(), bad)
        self.assertEqual(p["approval_status"], "rejected")
        self.assertEqual(p["deterministic_validation"]["status"], "rejected")

    def test_valid_proposal_pending(self):
        good = json.dumps(_proposal())
        p = self._run(_extraction(), good)
        self.assertEqual(p["deterministic_validation"]["status"], "validated")
        self.assertEqual(p["approval_status"], "pending")


class ApplyTests(unittest.TestCase):
    def test_apply_preserves_original(self):
        ext = _extraction()
        p = _proposal(proposed_financial_value=9_000_000_000,
                      financial_definition="unrestricted cash and cash equivalents",
                      category="cash_restricted_scope")
        out = apply_correction(ext, p)
        # original untouched
        self.assertEqual(ext["cash_and_equivalents"], 10_000_000_000)
        self.assertEqual(out["original"]["cash_and_equivalents"], 10_000_000_000)
        # corrected snapshot updated: net debt = total debt (44e9) - cash (9e9) = 35e9
        self.assertEqual(out["corrected"]["cash_and_equivalents"], 9_000_000_000)
        self.assertEqual(out["corrected"]["net_debt"], 35_000_000_000)
        self.assertEqual(out["impact"]["net_debt_delta"], 1_000_000_000)

    def test_apply_net_debt_metric(self):
        ext = _extraction()
        p = _proposal(proposed_financial_value=45_714_000_000,
                      financial_definition="net debt including short-term borrowings")
        out = apply_correction(ext, p)
        self.assertEqual(out["corrected"]["net_debt"], 45_714_000_000)
        self.assertEqual(out["impact"]["metric"], "net_debt")

    def test_debt_less_cash_classified_as_net_debt(self):
        # "debt less cash" is a NET debt figure; must not subtract cash a second time.
        from autoval.reconciliation.apply import _classify_metric
        self.assertEqual(_classify_metric("Debt less cash as reconstructed", ""), "net_debt")
        self.assertEqual(_classify_metric("total debt net of cash and equivalents", ""), "net_debt")
        self.assertEqual(_classify_metric("gross debt", ""), "total_debt")

    def test_debt_component_cannot_be_applied_as_complete_debt(self):
        # A single debt component (e.g. short-term borrowings) must not be applied as a
        # complete total/net debt figure (CSCO holdout case).
        from autoval.reconciliation.apply import _classify_metric
        self.assertEqual(_classify_metric(
            "short-term borrowings / commercial paper outstanding", ""), "component")
        p = _proposal(financial_definition="short-term borrowings / commercial paper outstanding",
                      proposed_financial_value=8_424_000_000, category="debt_unavailable")
        p["approval_status"] = "approved"
        p["deterministic_validation"] = {"status": "validated", "checks": []}
        r = apply_approved(p, _extraction(), "s1")
        self.assertEqual(r["status"], "rejected")
        self.assertIn("component", r["reason"])


class MarketDataCarryForwardTests(unittest.TestCase):
    """Two carried-forward market-data regression requirements (must remain true)."""

    def test_missing_market_data_does_not_introduce_assumed_wacc(self):
        from autoval.market_data import classify_wacc
        # Missing market price -> equity value unavailable -> never 'company-specific'.
        wacc_block = {"available": False, "inputs": {
            "beta": {"available": True}, "equity_value": {"available": False}}}
        self.assertEqual(classify_wacc(wacc_block, True, False), "unavailable")

    def test_missing_target_price_does_not_invalidate_peer_implied(self):
        from autoval.relative import pe_summary, ev_ebitda_summary
        # Peer-implied P/E uses peer multiples + target EPS (NOT the target price).
        pe = pe_summary([18.0, 20.0, 22.0], 4.0)
        self.assertIsNotNone(pe["implied_price_median"])
        self.assertIsNotNone(pe["implied_price_p25"])
        self.assertIsNotNone(pe["implied_price_p75"])
        # EV/EBITDA implied price uses EBITDA + net debt + shares, not target price.
        ev = ev_ebitda_summary([8.0, 9.0, 10.0], 5e9, 10e9, 1e9)
        self.assertIsNotNone(ev["implied_price_median"])

    def test_public_demo_blocks_paid_llm_even_with_credentials(self):
        from autoval.reconciliation import llm as llm_mod
        with patch.dict("os.environ", {"AUTOVAL_PUBLIC_DEMO": "1", "AUTOVAL_LLM_API_KEY": "sk-test"}):
            with patch("requests.post") as mock_post:
                with self.assertRaisesRegex(RuntimeError, "public demonstration"):
                    llm_mod.chat([{"role": "user", "content": "hi"}])
                mock_post.assert_not_called()  # transport never reached


class SafetyTests(unittest.TestCase):
    """Deterministic validation must check retrieved source FACTS, not just citations."""

    def _facts_with(self, *tag_val_end_filed):
        us = {}
        for tag, val, end, filed in tag_val_end_filed:
            us[tag] = {"units": {"USD": [{"end": end, "filed": filed, "val": val,
                                          "form": "10-K"}]}}
        return {"facts": {"us-gaap": us, "dei": {}}}

    def test_correct_url_wrong_value_rejected(self):
        facts = self._facts_with(
            ("LongTermDebtNoncurrent", 30e9, "2026-06-30", "2026-08-04"),
            ("LongTermDebtCurrent", 2e9, "2026-06-30", "2026-08-04"),
            ("CashAndCashEquivalentsAtCarryingValue", 10e9, "2026-06-30", "2026-08-04"))
        # proposal cites LongTermDebtNoncurrent = 40e9, but companyfacts has 30e9
        p = _proposal()
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("source_fact_value", r["hard_failures"])

    def test_wrong_company_rejected(self):
        facts = self._facts_with(
            ("LongTermDebtNoncurrent", 40e9, "2026-06-30", "2026-08-04"),
            ("LongTermDebtCurrent", 2e9, "2026-06-30", "2026-08-04"),
            ("CashAndCashEquivalentsAtCarryingValue", 10e9, "2026-06-30", "2026-08-04"))
        p = _proposal(ticker="WMT")  # extraction is PG
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("company_identity", r["hard_failures"])

    def test_restricted_cash_treated_as_unrestricted_unresolved(self):
        facts = self._facts_with(
            ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
             15e9, "2026-06-30", "2026-08-04"))
        p = _proposal(
            financial_definition="unrestricted cash and cash equivalents",
            proposed_financial_value=15e9,
            derivation_formula="CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            xbrl_tags=[{"tag": "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                        "value": 15e9, "period_end": "2026-06-30",
                        "filed": "2026-08-04", "form": "10-K"}])
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "unresolved")
        self.assertIn("restricted_cash", r["soft_warnings"])

    def test_malicious_instruction_in_formula_rejected(self):
        facts = self._facts_with(
            ("LongTermDebtNoncurrent", 40e9, "2026-06-30", "2026-08-04"))
        p = _proposal(derivation_formula="__import__('os').system('rm -rf /')",
                      xbrl_tags=[{"tag": "LongTermDebtNoncurrent", "value": 40e9,
                                  "period_end": "2026-06-30", "filed": "2026-08-04",
                                  "form": "10-K"}])
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("component_arithmetic", r["hard_failures"])

    def test_unsupported_expression_rejected(self):
        from autoval.reconciliation.validate import _safe_eval
        with self.assertRaises(ValueError):
            _safe_eval("A.__class__", {"A": 1})
        with self.assertRaises(ValueError):
            _safe_eval("open('/etc/passwd')", {})


class ApprovalBindingTests(unittest.TestCase):
    def _approved(self, **overrides):
        p = _proposal(**overrides)
        p["approval_status"] = "approved"
        p["deterministic_validation"] = {"status": "validated", "checks": []}
        return p

    def test_not_approved_rejected(self):
        p = _proposal()  # approval_status = pending
        self.assertEqual(apply_approved(p, _extraction(), "s1")["status"], "rejected")

    def test_unvalidated_rejected(self):
        p = _proposal(approval_status="approved")
        p["deterministic_validation"] = {"status": "rejected", "checks": []}
        self.assertEqual(apply_approved(p, _extraction(), "s1")["status"], "rejected")

    def test_outdated_snapshot_rejected(self):
        p = self._approved(reporting_period="2025-12-31")
        self.assertEqual(apply_approved(p, _extraction(), "s1")["status"], "rejected")

    def test_duplicate_application_rejected(self):
        p = self._approved()
        p["applied_snapshot_id"] = "s0"
        self.assertEqual(apply_approved(p, _extraction(), "s1")["status"], "rejected")

    def test_no_correction_leaves_unchanged(self):
        p = self._approved()
        p["proposed_financial_value"] = p["original_production_value"]
        r = apply_approved(p, _extraction(), "s1")
        self.assertEqual(r["status"], "no_change")
        self.assertEqual(r["impact"]["net_debt_delta"], 0.0)

    def test_apply_sets_snapshot_id(self):
        p = self._approved(financial_definition="net debt",
                           proposed_financial_value=35_000_000_000)
        r = apply_approved(p, _extraction(), "snap1")
        self.assertEqual(r["status"], "applied")
        self.assertEqual(p["applied_snapshot_id"], "snap1")
        self.assertIsNotNone(r["impact"]["net_debt_delta"])


class RegenerateTests(unittest.TestCase):
    def test_recompute_wacc_reflects_debt_change(self):
        stock = {"market_price": 100.0, "shares": 1e9, "total_debt": 50e9,
                 "source": {"annual_records": [{"interest": {"value": 2e9}}]}}
        wacc_block = {"available": True, "inputs": {
            "risk_free_rate": {"value": 0.05, "available": True},
            "beta": {"value": 1.0, "available": True},
            "equity_risk_premium": {"value": 0.05, "available": True},
            "marginal_tax_rate": {"value": 0.21, "available": True}}}
        w1 = recompute_wacc(stock, wacc_block)
        stock2 = dict(stock, total_debt=100e9)
        w2 = recompute_wacc(stock2, wacc_block)
        self.assertTrue(w1["available"] and w2["available"])
        # higher debt -> higher debt weight
        self.assertGreater(w2["calculation"]["debt_weight"], w1["calculation"]["debt_weight"])

    def test_regenerate_recomputes_net_debt_and_wacc(self):
        import os, json
        from tests.provider_fixture import build_from_fixture
        result, prices = build_from_fixture("MSFT")
        fx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "fixtures", "MSFT.json")))
        stock = fx["stock"]
        original_net_debt = stock["net_debt"]
        prop = {"ticker": "MSFT", "financial_definition": "net debt",
                "proposed_financial_value": original_net_debt + 10e9,
                "category": "net_debt_historical_discrepancy"}
        corrected_stock = apply_correction(stock, prop)["corrected"]
        self.assertNotEqual(corrected_stock["net_debt"], original_net_debt)
        r2 = regenerate_analysis(result, corrected_stock)
        self.assertTrue(r2.get("reconciled"))
        # corrected base-case net debt reflects the correction
        self.assertNotEqual(r2["analysis"]["scenarios"]["base"]["net_debt_usd"],
                            result["analysis"]["scenarios"]["base"]["net_debt_usd"])
        # original result unchanged
        self.assertEqual(result["analysis"]["scenarios"]["base"]["net_debt_usd"], original_net_debt)


class FilingEvidenceTests(unittest.TestCase):
    """Original-filing inline-XBRL extraction: contexts, scale, sign, units, period."""

    HTML = """
    <xbrli:context id="c1"><xbrli:entity>e</xbrli:entity>
      <xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context>
    <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="us-gaap:LongTermDebtNoncurrent" contextRef="c1" unitRef="usd"
                    scale="6" decimals="-6">21,897</ix:nonFraction>
    <ix:nonFraction name="us-gaap:DebtCurrent" contextRef="c1" unitRef="usd" scale="6"
                    decimals="-6" sign="-">17,028</ix:nonFraction>
    <ix:nonFraction name="us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
                    contextRef="c1" unitRef="usd" scale="6" decimals="-6">15,365</ix:nonFraction>
    """

    def test_extract_scale_sign_context_unit(self):
        from autoval.reconciliation.filing import extract_inline_facts, extract_contexts, extract_units, resolve_fact
        contexts = extract_contexts(self.HTML)
        units = extract_units(self.HTML)
        facts = {f["tag"]: resolve_fact(f, contexts, units) for f in extract_inline_facts(self.HTML)}
        self.assertEqual(facts["LongTermDebtNoncurrent"]["value"], 21_897_000_000.0)
        self.assertEqual(facts["DebtCurrent"]["value"], -17_028_000_000.0)  # sign="-"
        self.assertEqual(facts["LongTermDebtNoncurrent"]["period_end"], "2026-09-30")
        self.assertEqual(facts["LongTermDebtNoncurrent"]["unit"], "USD")

    def test_lookup_fact_at_period_and_wrong_context(self):
        from autoval.reconciliation.filing import lookup_fact
        self.assertEqual(lookup_fact(self.HTML, "LongTermDebtNoncurrent", "2026-09-30")["value"],
                         21_897_000_000.0)
        self.assertIsNone(lookup_fact(self.HTML, "LongTermDebtNoncurrent", "2025-12-31"))
        self.assertIsNone(lookup_fact(self.HTML, "ShortTermBorrowings"))

    def test_filing_fact_cross_check_rejects_wrong_value(self):
        from autoval.reconciliation.filing import extract_inline_facts, extract_contexts, extract_units, resolve_fact
        contexts = extract_contexts(self.HTML)
        units = extract_units(self.HTML)
        filing_facts = {f["tag"]: resolve_fact(f, contexts, units) for f in extract_inline_facts(self.HTML)}
        facts = self._facts_with(("LongTermDebtNoncurrent", 21_897_000_000.0, "2026-06-30", "2026-08-04"))
        # cite the correct companyfacts value but a WRONG value vs the inline filing
        p = _proposal(xbrl_tags=[{"tag": "LongTermDebtNoncurrent", "value": 21_897_000_000.0,
                                  "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"}])
        # companyfacts says 21.897B (matches), but filing inline has 21.897B too -> valid.
        # Force a mismatch by citing a different value.
        p["xbrl_tags"] = [{"tag": "LongTermDebtNoncurrent", "value": 30e9,
                           "period_end": "2026-06-30", "filed": "2026-08-04", "form": "10-K"}]
        r = validate(p, _extraction(), facts, filing_facts=filing_facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("source_fact_value", r["hard_failures"])

    def test_custom_taxonomy_tag_accepted_via_filing_fact(self):
        # A tag present in the original filing but NOT in Companyfacts must still validate.
        filing_facts = {"LongTermNotesAndLoans": {"name": "us-gaap:LongTermNotesAndLoans",
                                                 "value": 117_712_000_000.0, "unit": "USD",
                                                 "period_end": "2026-08-31"}}
        facts = {"facts": {"us-gaap": {}, "dei": {}}}  # empty companyfacts
        p = _proposal(
            proposed_financial_value=117_712_000_000.0,
            derivation_formula="LongTermNotesAndLoans",
            xbrl_tags=[{"tag": "LongTermNotesAndLoans", "value": 117_712_000_000.0,
                        "period_end": "2026-08-31", "filed": "2026-09-15", "form": "10-Q"}])
        r = validate(p, _extraction(), facts, filing_facts=filing_facts)
        self.assertEqual(r["status"], "validated", r["checks"])

    def test_unsupported_custom_tag_still_rejected(self):
        # No Companyfacts entry AND no filing fact -> the tag cannot be validated.
        facts = {"facts": {"us-gaap": {}, "dei": {}}}
        p = _proposal(xbrl_tags=[{"tag": "CustomCompanyTag", "value": 1e9,
                                  "period_end": "2026-06-30", "filed": "2026-08-04",
                                  "form": "10-K"}])
        r = validate(p, _extraction(), facts)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("xbrl_tag_exists", r["hard_failures"])

    def _facts_with(self, *tag_val_end_filed):
        us = {}
        for tag, val, end, filed in tag_val_end_filed:
            us[tag] = {"units": {"USD": [{"end": end, "filed": filed, "val": val, "form": "10-K"}]}}
        return {"facts": {"us-gaap": us, "dei": {}}}


if __name__ == "__main__":
    unittest.main()
