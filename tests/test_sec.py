import unittest
from unittest.mock import patch
from autoval.sec import annual_values, latest_instant, get_sec_financials


def annual(val, end, filed="2026-02-01"):
    return {"start":end[:4]+"-01-01", "end":end, "form":"10-K", "filed":filed, "val":val}

def instant(val,end="2025-12-31",filed="2026-02-01"):
    return {"end":end,"form":"10-K","filed":filed,"val":val}


def fixture():
    ends=["2023-12-31","2024-12-31","2025-12-31"]
    names={
        "NetCashProvidedByUsedInOperatingActivities":[150,162,180],
        "PaymentsToAcquirePropertyPlantAndEquipment":[30,32,36],
        "InterestExpenseNonoperating":[10,11,12],
        "IncomeTaxExpenseBenefit":[20,22,25],
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":[100,110,125],
        "NetIncomeLoss":[80,88,100],
        "OperatingIncomeLoss":[120,135,150],
        "DepreciationDepletionAndAmortization":[20,21,22],
    }
    x={"facts":{"us-gaap":{},"dei":{}}}
    for name, vals in names.items():
        x["facts"]["us-gaap"][name]={"units":{"USD":[annual(v,e) for v,e in zip(vals,ends)]}}
    for name,val in [("CashAndCashEquivalentsAtCarryingValue",50),
                     ("LongTermDebtNoncurrent",60),
                     ("LongTermDebtCurrent",4)]:
        x["facts"]["us-gaap"][name]={"units":{"USD":[instant(val)]}}
    x["facts"]["dei"]["EntityCommonStockSharesOutstanding"]={"units":{"shares":[instant(10)]}}
    return x

class SecTests(unittest.TestCase):
    def test_annual_periods(self):
        x=fixture()
        v=annual_values(x,("NetCashProvidedByUsedInOperatingActivities",),today="2026-11-11")
        self.assertEqual(len(v),3)
        self.assertEqual(v["2025-12-31"]["value"],180)

    def test_instant_asof(self):
        x=fixture()
        s=latest_instant(x,"dei",("EntityCommonStockSharesOutstanding",),"shares",today="2026-11-11")
        self.assertEqual(s["value"],10)

    @patch("autoval.sec.fetch_json")
    def test_parses_mocked_sec_statements(self, fetch):
        fetch.side_effect=[{"0":{"ticker":"MOCK","cik_str":123,"title":"Mock Company"}}, fixture()]
        out=get_sec_financials("MOCK","Example example@example.com")
        self.assertAlmostEqual(out["fcff_history"][-1]["fcff_usd"],153.6) # 180 - 36 + 12*(1-.2)
        self.assertAlmostEqual(out["net_debt"],14)
        self.assertEqual(out["shares"],10)

    @patch("autoval.sec.fetch_json")
    def test_refuses_missing_critical_interest_expense(self, fetch):
        x=fixture()
        x["facts"]["us-gaap"].pop("InterestExpenseNonoperating")
        fetch.side_effect=[{"0":{"ticker":"MOCK","cik_str":123,"title":"Mock Company"}}, x]
        with self.assertRaisesRegex(ValueError,"Insufficient matched annual SEC facts"):
            get_sec_financials("MOCK","Example example@example.com")

    @patch("autoval.sec.fetch_json")
    def test_capex_alternative_tag(self, fetch):
        x=fixture()
        u=x["facts"]["us-gaap"]
        u.pop("PaymentsToAcquirePropertyPlantAndEquipment")
        ends=["2023-12-31","2024-12-31","2025-12-31"]
        u["PaymentsToAcquireProductiveAssets"]={"units":{"USD":[annual(v,e) for v,e in zip([30,32,36],ends)]}}
        fetch.side_effect=[{"0":{"ticker":"MOCK","cik_str":123,"title":"Mock Company"}}, x]
        out=get_sec_financials("MOCK","Example example@example.com")
        self.assertAlmostEqual(out["fcff_history"][-1]["fcff_usd"],153.6)  # 180-36+12*.8

    @patch("autoval.sec.fetch_json")
    def test_capex_no_double_count(self, fetch):
        x=fixture()  # primary capex [30,32,36]
        ends=["2023-12-31","2024-12-31","2025-12-31"]
        x["facts"]["us-gaap"]["PaymentsToAcquireProductiveAssets"]={"units":{"USD":[annual(999,e) for e in ends]}}
        fetch.side_effect=[{"0":{"ticker":"MOCK","cik_str":123,"title":"Mock Company"}}, x]
        out=get_sec_financials("MOCK","Example example@example.com")
        self.assertAlmostEqual(out["fcff_history"][-1]["fcff_usd"],153.6)  # primary 36 wins, not 36+999

    @patch("autoval.sec.fetch_json")
    def test_capex_both_missing_raises(self, fetch):
        x=fixture()
        x["facts"]["us-gaap"].pop("PaymentsToAcquirePropertyPlantAndEquipment")
        fetch.side_effect=[{"0":{"ticker":"MOCK","cik_str":123,"title":"Mock Company"}}, x]
        with self.assertRaisesRegex(ValueError,"Insufficient matched annual SEC facts"):
            get_sec_financials("MOCK","Example example@example.com")

class DebtReconciliationTests(unittest.TestCase):
    def _get(self, facts):
        with patch("autoval.sec.fetch_json") as fetch:
            fetch.side_effect = [{"0": {"ticker": "MOCK", "cik_str": 123, "title": "Mock Company"}}, facts]
            return get_sec_financials("MOCK", "Example example@example.com")

    def _facts(self, long_entries=None, current_entries=None, short_entries=None):
        x = fixture()
        us = x["facts"]["us-gaap"]
        us["CashAndCashEquivalentsAtCarryingValue"] = {"units": {"USD": [instant(50, "2025-12-31")]}}
        us["LongTermDebtNoncurrent"] = {"units": {"USD": long_entries or [instant(60, "2025-12-31")]}}
        us.pop("LongTermDebtCurrent", None)
        us.pop("ShortTermBorrowings", None)
        if current_entries is not None:
            us["LongTermDebtCurrent"] = {"units": {"USD": current_entries}}
        if short_entries is not None:
            us["ShortTermBorrowings"] = {"units": {"USD": short_entries}}
        return x

    def test_consistent_current_debt_components(self):
        out = self._get(self._facts(current_entries=[instant(4, "2025-12-31")]))
        self.assertAlmostEqual(out["net_debt"], 14)  # 60 + 4 - 50
        rec = out["source"]["debt_reconciliation"]
        self.assertEqual(rec["long_term_debt"], 60)
        self.assertEqual(rec["current_portion_long_term_debt"], 4)
        self.assertEqual(rec["short_term_borrowings"], 0)
        statuses = {e["tag"]: e["status"] for e in out["source"]["excluded_debt_tags"]}
        self.assertEqual(statuses.get("ShortTermBorrowings"), "absent")

    def test_stale_zero_short_term_borrowings_excluded(self):
        facts = self._facts(current_entries=[instant(4, "2025-12-31")],
                            short_entries=[instant(0, "2018-06-30", filed="2018-08-03")])
        out = self._get(facts)
        self.assertAlmostEqual(out["net_debt"], 14)  # stale zero excluded, not summed
        ex = {e["tag"]: e for e in out["source"]["excluded_debt_tags"]}
        self.assertEqual(ex["ShortTermBorrowings"]["status"], "stale_zero")
        self.assertEqual(ex["ShortTermBorrowings"]["last_value"], 0)
        self.assertTrue(any("stale" in w for w in out["source"]["disclosure_warnings"]))

    def test_stale_nonzero_borrowings_raise(self):
        facts = self._facts(current_entries=[instant(4, "2025-12-31")],
                            short_entries=[instant(5000, "2018-06-30", filed="2018-08-03")])
        with self.assertRaisesRegex(ValueError, "cannot reconcile"):
            self._get(facts)

    def test_missing_long_term_debt_raises(self):
        facts = self._facts()
        facts["facts"]["us-gaap"].pop("LongTermDebtNoncurrent")
        with self.assertRaisesRegex(ValueError, "not reported at cash reporting date"):
            self._get(facts)

    def test_no_double_counting_same_period_filings(self):
        # Same tag reported in two filings at one period end: only the freshest is used.
        facts = self._facts(long_entries=[instant(60, "2025-12-31", filed="2026-02-01"),
                                          instant(65, "2025-12-31", filed="2026-05-01")],
                            current_entries=[instant(4, "2025-12-31")])
        out = self._get(facts)
        self.assertEqual(out["source"]["long_debt"]["value"], 65)
        self.assertAlmostEqual(out["net_debt"], 19)  # 65 + 4 - 50 (not 60+65+4-50)

    def test_debt_alternative_tags(self):
        # HD-style: lease-inclusive long-term debt + current portion + commercial paper.
        x = fixture()
        us = x["facts"]["us-gaap"]
        us["CashAndCashEquivalentsAtCarryingValue"] = {"units": {"USD": [instant(2085, "2026-08-02")]}}
        us.pop("LongTermDebtNoncurrent", None)
        us.pop("LongTermDebtCurrent", None)
        us.pop("ShortTermBorrowings", None)
        us["LongTermDebtAndCapitalLeaseObligations"] = {"units": {"USD": [instant(43951, "2026-08-02")]}}
        us["LongTermDebtAndCapitalLeaseObligationsCurrent"] = {"units": {"USD": [instant(4697, "2026-08-02")]}}
        us["CommercialPaper"] = {"units": {"USD": [instant(4248, "2026-08-02")]}}
        out = self._get(x)
        self.assertAlmostEqual(out["total_debt"], 43951 + 4697 + 4248)
        self.assertAlmostEqual(out["net_debt"], 43951 + 4697 + 4248 - 2085)

    def test_debt_stale_noncurrent_prefers_current(self):
        # LongTermDebtNoncurrent is stale (2011); lease-inclusive tag is current -> use current.
        x = fixture()
        us = x["facts"]["us-gaap"]
        us["CashAndCashEquivalentsAtCarryingValue"] = {"units": {"USD": [instant(2085, "2026-08-02")]}}
        us["LongTermDebtNoncurrent"] = {"units": {"USD": [instant(8707, "2011-01-30", filed="2011-03-01")]}}
        us.pop("LongTermDebtCurrent", None)
        us.pop("ShortTermBorrowings", None)
        us["LongTermDebtAndCapitalLeaseObligations"] = {"units": {"USD": [instant(43951, "2026-08-02")]}}
        out = self._get(x)
        self.assertEqual(out["source"]["long_debt"]["value"], 43951)
        self.assertAlmostEqual(out["net_debt"], 43951 - 2085)

    def test_debt_no_double_count_aggregate_vs_component(self):
        # Both tags at the same date: primary (LongTermDebtNoncurrent) wins, not summed.
        x = fixture()
        us = x["facts"]["us-gaap"]
        us["CashAndCashEquivalentsAtCarryingValue"] = {"units": {"USD": [instant(50, "2025-12-31")]}}
        us["LongTermDebtNoncurrent"] = {"units": {"USD": [instant(60, "2025-12-31")]}}
        us["LongTermDebtAndCapitalLeaseObligations"] = {"units": {"USD": [instant(999, "2025-12-31")]}}
        out = self._get(x)
        self.assertEqual(out["source"]["long_debt"]["value"], 60)
        self.assertAlmostEqual(out["net_debt"], 60 + 4 - 50)  # 60 not 60+999


class InterestTagTests(unittest.TestCase):
    def _fy(self, val, end, filed):
        y = int(end[:4])
        return {"start": f"{y-1}-07-01", "end": end, "form": "10-K", "filed": filed, "val": val}

    def test_per_year_interest_tag_fallback(self):
        x = {"facts": {"us-gaap": {}}}
        u = x["facts"]["us-gaap"]
        u["InterestExpense"] = {"units": {"USD": [
            self._fy(2346, "2021-06-30", "2021-07-29"),
            self._fy(2063, "2022-06-30", "2022-07-28"),
        ]}}
        u["InterestExpenseNonoperating"] = {"units": {"USD": [
            self._fy(2935, "2024-06-30", "2025-07-30"),
            self._fy(2385, "2025-06-30", "2026-07-29"),
            self._fy(3051, "2026-06-30", "2026-07-29"),
        ]}}
        v = annual_values(x, ("InterestExpenseNonoperating", "InterestExpense"), today="2026-11-11")
        self.assertEqual(sorted(v), ["2021-06-30", "2022-06-30", "2024-06-30", "2025-06-30", "2026-06-30"])
        self.assertEqual(v["2021-06-30"]["tag"], "InterestExpense")
        self.assertEqual(v["2021-06-30"]["value"], 2346)
        self.assertEqual(v["2024-06-30"]["tag"], "InterestExpenseNonoperating")
        self.assertEqual(v["2026-06-30"]["tag"], "InterestExpenseNonoperating")
        self.assertEqual(v["2026-06-30"]["value"], 3051)

    def test_priority_first_tag_wins_same_year(self):
        x = {"facts": {"us-gaap": {}}}
        u = x["facts"]["us-gaap"]
        u["InterestExpenseNonoperating"] = {"units": {"USD": [self._fy(3051, "2026-06-30", "2026-07-29")]}}
        u["InterestExpense"] = {"units": {"USD": [self._fy(9999, "2026-06-30", "2026-07-29")]}}
        v = annual_values(x, ("InterestExpenseNonoperating", "InterestExpense"), today="2026-11-11")
        self.assertEqual(v["2026-06-30"]["tag"], "InterestExpenseNonoperating")
        self.assertEqual(v["2026-06-30"]["value"], 3051)

    def test_wrong_casing_tag_is_ignored(self):
        x = {"facts": {"us-gaap": {"InterestExpenseNonOperating": {"units": {"USD": [
            self._fy(9999, "2026-06-30", "2026-07-29")]}}}}}
        v = annual_values(x, ("InterestExpenseNonoperating", "InterestExpense"), today="2026-11-11")
        self.assertEqual(v, {})

    def test_missing_interest_tags_return_empty(self):
        x = {"facts": {"us-gaap": {}}}
        v = annual_values(x, ("InterestExpenseNonoperating", "InterestExpense"), today="2026-11-11")
        self.assertEqual(v, {})

    def test_short_period_excluded(self):
        x = {"facts": {"us-gaap": {"InterestExpenseNonoperating": {"units": {"USD": [
            {"start": "2026-01-01", "end": "2026-06-30", "form": "10-K", "filed": "2026-07-29", "val": 999},
            self._fy(3051, "2026-06-30", "2026-07-29"),
        ]}}}}}
        v = annual_values(x, ("InterestExpenseNonoperating", "InterestExpense"), today="2026-11-11")
        self.assertEqual(list(v), ["2026-06-30"])
        self.assertEqual(v["2026-06-30"]["value"], 3051)

    @patch("autoval.sec.fetch_json")
    def test_fcff_with_mixed_interest_tags(self, fetch):
        ends = ["2023-06-30", "2024-06-30", "2025-06-30", "2026-06-30"]
        x = {"facts": {"us-gaap": {}, "dei": {}}}
        u = x["facts"]["us-gaap"]
        u["NetCashProvidedByUsedInOperatingActivities"] = {"units": {"USD": [self._fy(v, e, "2026-07-29") for v, e in zip([80, 90, 100, 110], ends)]}}
        u["PaymentsToAcquirePropertyPlantAndEquipment"] = {"units": {"USD": [self._fy(v, e, "2026-07-29") for v, e in zip([20, 25, 30, 35], ends)]}}
        u["InterestExpense"] = {"units": {"USD": [self._fy(5, "2023-06-30", "2024-07-30")]}}
        u["InterestExpenseNonoperating"] = {"units": {"USD": [self._fy(6, "2024-06-30", "2025-07-30"),
                                                                 self._fy(7, "2025-06-30", "2026-07-29"),
                                                                 self._fy(8, "2026-06-30", "2026-07-29")]}}
        u["IncomeTaxExpenseBenefit"] = {"units": {"USD": [self._fy(20, e, "2026-07-29") for e in ends]}}
        u["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"] = {"units": {"USD": [self._fy(100, e, "2026-07-29") for e in ends]}}
        u["CashAndCashEquivalentsAtCarryingValue"] = {"units": {"USD": [instant(50, "2026-09-30")]}}
        u["LongTermDebtNoncurrent"] = {"units": {"USD": [instant(60, "2026-09-30")]}}
        x["facts"]["dei"]["EntityCommonStockSharesOutstanding"] = {"units": {"shares": [instant(10, "2026-09-30")]}}
        fetch.side_effect = [{"0": {"ticker": "MOCK", "cik_str": 123, "title": "Mock Company"}}, x]
        out = get_sec_financials("MOCK", "Example example@example.com")
        hist = out["fcff_history"]
        self.assertEqual([h["year_end"] for h in hist], ends)
        # FCFF = CFO - capex + interest*(1 - 20%)
        self.assertAlmostEqual(hist[0]["fcff_usd"], 64.0)   # 80 - 20 + 5*0.8
        self.assertAlmostEqual(hist[-1]["fcff_usd"], 81.4)  # 110 - 35 + 8*0.8


class InvestmentFactsTests(unittest.TestCase):
    def _run(self, facts):
        with patch("autoval.sec.fetch_json") as fetch:
            fetch.side_effect = [{"0": {"ticker": "MOCK", "cik_str": 123, "title": "Mock Company"}}, facts]
            return get_sec_financials("MOCK", "Example example@example.com")

    def test_investments_absent_treated_as_none(self):
        out = self._run(fixture())  # fixture() has no investment tags
        self.assertIsNone(out["short_term_investments"])
        self.assertIsNone(out["restricted_investments"])
        self.assertIsNone(out["long_term_investments"])
        statuses = {e["tag"]: e["status"] for e in out["source"]["excluded_investment_tags"]}
        self.assertEqual(statuses.get("ShortTermInvestments"), "absent")
        self.assertTrue(out["source"]["investment_assumptions"])

    def test_investments_present(self):
        x = fixture()
        us = x["facts"]["us-gaap"]
        us["ShortTermInvestments"] = {"units": {"USD": [instant(44, "2025-12-31")]}}
        us["RestrictedInvestments"] = {"units": {"USD": [instant(12, "2025-12-31")]}}
        us["LongTermInvestments"] = {"units": {"USD": [instant(37, "2025-12-31")]}}
        out = self._run(x)
        self.assertEqual(out["short_term_investments"], 44)
        self.assertEqual(out["restricted_investments"], 12)
        self.assertEqual(out["long_term_investments"], 37)
        self.assertEqual(out["total_debt"], 64)   # 60 long + 4 current + 0 short
        self.assertEqual(out["cash_and_equivalents"], 50)

    def test_stale_investment_excluded(self):
        x = fixture()
        x["facts"]["us-gaap"]["ShortTermInvestments"] = {
            "units": {"USD": [instant(999, "2018-06-30", filed="2018-08-03")]}}
        out = self._run(x)
        self.assertIsNone(out["short_term_investments"])  # stale -> excluded/zero
        ex = {e["tag"]: e for e in out["source"]["excluded_investment_tags"]}
        self.assertEqual(ex["ShortTermInvestments"]["status"], "stale")


    @patch("autoval.sec.fetch_json")
    def test_cash_interest_paid_used_in_fcff(self, fetch):
        x = fixture()
        ends = ["2023-12-31", "2024-12-31", "2025-12-31"]
        # cash interest paid (10) differs from interest expense (12)
        x["facts"]["us-gaap"]["InterestPaidNet"] = {"units": {"USD": [annual(10, e) for e in ends]}}
        fetch.side_effect = [{"0": {"ticker": "MOCK", "cik_str": 123, "title": "Mock Company"}}, x]
        out = get_sec_financials("MOCK", "Example example@example.com")
        # latest year FCFF = 180 - 36 + 10*(1-0.2) = 152.0 (using cash interest paid)
        self.assertAlmostEqual(out["fcff_history"][-1]["fcff_usd"], 152.0)
        rec = out["source"]["annual_records"][-1]
        self.assertEqual(rec["interest_addback"], 10)
        self.assertEqual(rec["interest_addback_note"], "cash interest paid")


if __name__=="__main__": unittest.main()
