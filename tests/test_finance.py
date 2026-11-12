import unittest
from autoval.finance import fcff_from_us_gaap_cashflows, dcf_fcff, analyze_valuation, derive_scenarios, equity_bridge
from autoval.pipeline import build_analysis
from verify_output import check_report


class FinanceTests(unittest.TestCase):
    def test_fcff_interest_tax(self):
        self.assertAlmostEqual(fcff_from_us_gaap_cashflows(100,20,10,.2),88)

    def test_reference_dcf_one_year(self):
        # 100 of annual cash flow forever, 10% discount, 10 shares -> 100/share.
        r=dcf_fcff(100,10,0,0,.1,0,years=1)
        self.assertAlmostEqual(r["enterprise_value_usd"],1000,places=7)
        self.assertAlmostEqual(r["intrinsic_per_share_usd"],100,places=7)

    def test_net_debt_bridge(self):
        r=dcf_fcff(100,10,100,0,.1,0,years=1)
        self.assertAlmostEqual(r["intrinsic_per_share_usd"],90)

    def test_invalid_discount_gap(self):
        with self.assertRaises(ValueError):
            dcf_fcff(100,10,0,.05,.03,.03)

    def test_invalid_fcff(self):
        with self.assertRaises(ValueError):
            derive_scenarios([-10,-20])

    def test_demo_generated_all_three_ordered(self):
        result, frame=build_analysis("DEMO","demo")
        a=result["analysis"]["scenarios"]
        self.assertLess(a["bear"]["intrinsic_per_share_usd"],a["base"]["intrinsic_per_share_usd"])
        self.assertLess(a["base"]["intrinsic_per_share_usd"],a["bull"]["intrinsic_per_share_usd"])
        self.assertEqual(result["mode"],"demo")
        self.assertAlmostEqual(float(frame["close"].iloc[-1]),result["analysis"]["market_price"])

    def test_independent_decimal_reference(self):
        result,_=build_analysis("DEMO","demo")
        checked=check_report(result)
        self.assertTrue(checked["passed"])

    def test_detects_tampered_value(self):
        result,_=build_analysis("DEMO","demo")
        result["analysis"]["scenarios"]["base"]["intrinsic_per_share_usd"]+=1.00
        self.assertFalse(check_report(result)["passed"])

class BridgeTests(unittest.TestCase):
    def test_arithmetic(self):
        b = equity_bridge(1000, 300, 100, 50, 20)
        self.assertEqual(b["equity_value_usd_cash_only"], 800)      # 1000-300+100
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["conservative"], 30)  # 50-20
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["upper"], 50)
        self.assertEqual(b["equity_value_usd"]["conservative"], 830)  # 800+30
        self.assertEqual(b["equity_value_usd"]["upper"], 850)         # 800+50
        self.assertIsNone(b["restricted_in_short_term_usd"])

    def test_reconciled_case(self):
        b = equity_bridge(1000, 300, 100, 50, 20, restricted_in_short_term=5)
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["reconciled"], 45)  # 50-5
        self.assertEqual(b["equity_value_usd"]["reconciled"], 845)  # 800+45
        self.assertEqual(b["restricted_in_short_term_usd"], 5)

    def test_missing_restricted_collapses_range(self):
        b = equity_bridge(1000, 300, 100, 50, None)
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["conservative"], 50)
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["upper"], 50)

    def test_no_double_count_cash(self):
        b = equity_bridge(1000, 300, 100, 50, 0)
        self.assertEqual(b["equity_value_usd_cash_only"], 800)  # cash added once
        self.assertEqual(b["equity_value_usd"]["upper"], 850)   # ST added once, not ST+cash

    def test_no_double_subtraction_restriction(self):
        b = equity_bridge(1000, 300, 100, 50, 20, restricted_in_short_term=5)
        self.assertEqual(b["eligible_nonoperating_securities_usd"]["reconciled"], 45)
        self.assertNotEqual(b["eligible_nonoperating_securities_usd"]["reconciled"],
                            b["eligible_nonoperating_securities_usd"]["conservative"])

    def test_invalid_negative_or_range(self):
        with self.assertRaises(ValueError):
            equity_bridge(1000, -300, 100, 50, 20)
        with self.assertRaises(ValueError):
            equity_bridge(1000, 300, 100, 50, 20, restricted_in_short_term=-1)
        with self.assertRaises(ValueError):
            equity_bridge(1000, 300, 100, 50, 20, restricted_in_short_term=999)  # > ST
        with self.assertRaises(ValueError):
            equity_bridge(1000, 300, 100, 50, 20, other_claims=-5)

    def test_analyze_valuation_adds_bridge_variants(self):
        stock = {
            "ticker": "X", "market_price": 100.0, "shares": 10,
            "net_debt": 20, "fcff_history": [
                {"year_end": "2023-12-31", "fcff_usd": 1000},
                {"year_end": "2024-12-31", "fcff_usd": 1100},
                {"year_end": "2025-12-31", "fcff_usd": 1200},
            ],
            "total_debt": 50, "cash_and_equivalents": 30,
            "short_term_investments": 40, "restricted_investments": 10,
            "long_term_investments": 25, "restricted_in_short_term": 4,
        }
        a = analyze_valuation(stock)
        self.assertIsNotNone(a["bridge"])
        base = a["scenarios"]["base"]
        for v in ("conservative", "upper", "reconciled"):
            self.assertIn(f"intrinsic_per_share_usd_{v}", base)
        # reconciled (subtract 4) > conservative (subtract 10)
        self.assertGreater(base["intrinsic_per_share_usd_reconciled"],
                           base["intrinsic_per_share_usd_conservative"])

    def test_missing_bridge_fields_no_bridge(self):
        stock = {
            "ticker": "X", "market_price": 100.0, "shares": 10,
            "net_debt": 20, "fcff_history": [
                {"year_end": "2023-12-31", "fcff_usd": 1000},
                {"year_end": "2024-12-31", "fcff_usd": 1100},
                {"year_end": "2025-12-31", "fcff_usd": 1200},
            ],
        }
        a = analyze_valuation(stock)
        self.assertIsNone(a["bridge"])
        base = a["scenarios"]["base"]
        self.assertIn("intrinsic_per_share_usd", base)
        self.assertNotIn("intrinsic_per_share_usd_conservative", base)


if __name__=="__main__": unittest.main()
