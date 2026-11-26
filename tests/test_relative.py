import unittest
from decimal import Decimal
from autoval.relative import (
    median, p25, p75, trailing_pe, pe_summary, ev_ebitda, ev_ebitda_summary,
    summarize_relative_valuation,
)
from autoval.peers import peer_groups, screen_peers


class PercentileTests(unittest.TestCase):
    def test_median(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        self.assertEqual(median([1, 2, 3]), 2)

    def test_quartiles(self):
        self.assertEqual(p25([1, 2, 3, 4, 5]), 2)
        self.assertEqual(p75([1, 2, 3, 4, 5]), 4)


class PeValuationTests(unittest.TestCase):
    def test_trailing_pe(self):
        self.assertAlmostEqual(trailing_pe(100, 5), 20)
        self.assertIsNone(trailing_pe(100, -5))   # negative EPS -> None
        self.assertIsNone(trailing_pe(100, 0))

    def test_pe_summary(self):
        s = pe_summary([20, 25, 30, 35], 10)
        self.assertEqual(s["sample_size"], 4)
        self.assertAlmostEqual(s["median_pe"], 27.5)
        self.assertAlmostEqual(s["implied_price_median"], 275)
        self.assertEqual(s["excluded_negative"], 0)

    def test_pe_summary_excludes_negative(self):
        s = pe_summary([20, -5, 30, None], 10)
        self.assertEqual(s["sample_size"], 2)  # -5 and None excluded

    def test_pe_summary_min_three_peer_median(self):
        # fewer than 3 eligible peers -> median/implied suppressed (never a 2-observation median)
        s = pe_summary([83.4, 12.9], 4.0)
        self.assertIsNone(s["median_pe"])
        self.assertIsNone(s["implied_price_median"])
        s3 = pe_summary([20, 25, 30], 4.0)
        self.assertIsNotNone(s3["median_pe"])

    def test_ev_ebitda_min_three_peer_median(self):
        s = ev_ebitda_summary([8, 9], 100, 200, 50)
        self.assertIsNone(s["median_ev_ebitda"])
        self.assertIsNone(s["implied_price_median"])


class EvEbitdaTests(unittest.TestCase):
    def test_ev_construction(self):
        # EV = mcap + debt + leases + pref + minority - cash
        mult, ev = ev_ebitda(1000, 200, 50, 0, 0, 100, 100)
        self.assertAlmostEqual(ev, 1000 + 200 + 50 - 100)
        self.assertAlmostEqual(mult, ev / 100)

    def test_ev_ebitda_missing_market_cap_returns_none(self):
        # a missing market cap must not be treated as zero (invalid multiple)
        self.assertIsNone(ev_ebitda(None, 200, 0, 0, 0, 100, 50))

    def test_negative_ebitda_returns_none(self):
        self.assertIsNone(ev_ebitda(1000, 200, 0, 0, 0, 100, -10))

    def test_ev_ebitda_summary_implied_price(self):
        s = ev_ebitda_summary([8, 10, 12], 100, 200, 50)
        # median 10 -> implied EV 1000 -> equity 800 -> price 16
        self.assertAlmostEqual(s["median_ev_ebitda"], 10)
        self.assertAlmostEqual(s["implied_ev_median"], 1000)
        self.assertAlmostEqual(s["implied_equity_median"], 800)
        self.assertAlmostEqual(s["implied_price_median"], 16)

    def test_decimal_verification(self):
        # Independently verify P/E and EV/EBITDA with Decimal arithmetic
        D = Decimal
        pe = trailing_pe(100, 5)
        self.assertAlmostEqual(pe, float(D("100") / D("5")))
        mult, ev = ev_ebitda(1000, 200, 50, 0, 0, 100, 100)
        ev_d = D("1000") + D("200") + D("50") - D("100")
        self.assertAlmostEqual(ev, float(ev_d))
        self.assertAlmostEqual(mult, float(ev_d / D("100")))


class PeerSelectionTests(unittest.TestCase):
    def test_peer_groups_msft(self):
        g = peer_groups("MSFT")
        self.assertEqual(g["core_software"], ["ORCL", "CRM", "ADBE"])
        self.assertEqual(g["supplemental_software"], ["NOW", "SAP"])
        self.assertEqual(g["cloud_platform"], ["AMZN", "GOOGL"])

    def test_unknown_ticker_no_peers(self):
        self.assertEqual(peer_groups("ZZZZ"), {})

    def test_screen_excludes_missing(self):
        peers = {
            "A": {"market_cap": 100, "ttm_eps": 5, "ttm_ebitda": 50, "ev": 200, "valued": True},
            "B": {"market_cap": None, "ttm_eps": 5, "ttm_ebitda": 50, "ev": 200, "valued": True},
            "C": {"market_cap": 100, "ttm_eps": 5, "ttm_ebitda": 50, "ev": 200, "valued": False},
        }
        r = screen_peers(peers)
        self.assertEqual(list(r["valid"]), ["A"])
        self.assertEqual(len(r["excluded"]), 2)


class SummarizeTests(unittest.TestCase):
    def test_summarize_groups(self):
        target = {"ttm_eps": 10, "ttm_ebitda": 100, "gross_debt": 200, "finance_leases": 0,
                  "preferred": 0, "minority": 0, "cash": 100, "ttm_diluted_shares": 50}
        peers = {
            "ORCL": {"ticker": "ORCL", "valued": True, "pe": 20, "ev_ebitda": 10,
                     "ttm_eps": 5, "ttm_ebitda": 50, "market_cap": 1000, "price_date": "2026-11-11",
                     "gross_debt": 100, "cash": 50, "reason": "ok"},
            "CRM": {"ticker": "CRM", "valued": True, "pe": 30, "ev_ebitda": 12,
                    "ttm_eps": 3, "ttm_ebitda": 40, "market_cap": 900, "price_date": "2026-11-11",
                    "gross_debt": 80, "cash": 40, "reason": "ok"},
            "ADBE": {"ticker": "ADBE", "valued": True, "pe": 40, "ev_ebitda": 14,
                     "ttm_eps": 2, "ttm_ebitda": 30, "market_cap": 800, "price_date": "2026-11-11",
                     "gross_debt": 60, "cash": 30, "reason": "ok"},
        }
        groups = summarize_relative_valuation(target, peers, {"core_software": ["ORCL", "CRM", "ADBE"]})
        g = groups["core_software"]
        self.assertEqual(g["sample_size"], 3)
        self.assertAlmostEqual(g["pe"]["median_pe"], 30)
        self.assertAlmostEqual(g["ev_ebitda"]["median_ev_ebitda"], 12)
        # median EV/EBITDA 12 * EBITDA 100 = 1200 EV - net debt (100) = 1100 / 50 = 22
        self.assertAlmostEqual(g["ev_ebitda"]["implied_price_median"], 22)


class ExtractionTests(unittest.TestCase):
    def _qf(self, val, end, days=90, filed="2026-05-01"):
        import datetime as dt
        d = dt.date.fromisoformat(end)
        s = (d - dt.timedelta(days=days)).isoformat()
        return {"start": s, "end": end, "form": "10-Q", "filed": filed, "val": val}

    def _facts(self, us_gaap):
        return {"facts": {"us-gaap": us_gaap, "dei": {}}}

    def _ttm(self, val, start, end, form="10-K", filed="2026-02-01"):
        return {"start": start, "end": end, "form": form, "filed": filed, "val": val}

    def test_ttm_da_prefers_total_tag(self):
        from autoval.relative_data import _ttm_da
        u = {
            "DepreciationAndAmortization": {"units": {"USD": [
                self._ttm(400, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
                self._ttm(250, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
                self._ttm(300, "2026-01-01", "2026-09-30", "10-Q", "2026-10-30"),
            ]}},
            "Depreciation": {"units": {"USD": [
                self._ttm(250, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
            ]}},
        }
        total, tag = _ttm_da(self._facts(u))
        # total tag used, NOT total + components (no double-count); TTM = 400 + 300 - 250
        self.assertEqual(tag, "DepreciationAndAmortization")
        self.assertAlmostEqual(total, 450)

    def test_ttm_da_component_fallback(self):
        from autoval.relative_data import _ttm_da
        u = {
            "Depreciation": {"units": {"USD": [
                self._ttm(250, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
                self._ttm(150, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
                self._ttm(180, "2026-01-01", "2026-09-30", "10-Q", "2026-10-30"),
            ]}},
            "AmortizationOfIntangibleAssets": {"units": {"USD": [
                self._ttm(100, "2025-01-01", "2025-12-31", "10-K", "2026-02-01"),
                self._ttm(60, "2025-01-01", "2025-09-30", "10-Q", "2025-10-30"),
                self._ttm(70, "2026-01-01", "2026-09-30", "10-Q", "2026-10-30"),
            ]}},
        }
        total, tag = _ttm_da(self._facts(u))
        # Depreciation TTM = 250 + 180 - 150 = 280; Amortization TTM = 100 + 70 - 60 = 110
        self.assertAlmostEqual(total, 280 + 110)
        self.assertIn("Depreciation", tag)
        self.assertIn("AmortizationOfIntangibleAssets", tag)

    def test_gross_debt_notes_payable(self):
        from autoval.relative_data import _gross_debt
        def inst(val, end, tag):
            return {"end": end, "form": "10-Q", "filed": "2026-05-01", "val": val, "tag": tag}
        u = {
            "LongTermNotesPayable": {"units": {"USD": [inst(122342, "2026-05-31", "LongTermNotesPayable")]}},
            "NotesPayableCurrent": {"units": {"USD": [inst(7625, "2026-05-31", "NotesPayableCurrent")]}},
        }
        self.assertAlmostEqual(_gross_debt(self._facts(u)), 122342 + 7625)

    def test_gross_debt_combined_total(self):
        from autoval.relative_data import _gross_debt
        def inst(val, end, tag):
            return {"end": end, "form": "10-Q", "filed": "2026-05-01", "val": val, "tag": tag}
        u = {"DebtLongtermAndShorttermCombinedAmount": {"units": {"USD": [inst(129541, "2026-05-31", "DebtLongtermAndShorttermCombinedAmount")]}}}
        self.assertAlmostEqual(_gross_debt(self._facts(u)), 129541)


if __name__ == "__main__":
    unittest.main()
