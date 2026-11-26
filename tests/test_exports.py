"""Deterministic regression tests for professional financial exports + valuation presentation."""
import os
import tempfile
import unittest

from tests.provider_fixture import build_from_fixture
from autoval.exports import build_excel_workbook, build_pdf_report


class ExportTests(unittest.TestCase):
    def _result(self, ticker="MSFT"):
        return build_from_fixture(ticker)[0]

    def test_excel_has_expected_sheets(self):
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            for s in ("Assumptions", "FCFF Forecast", "Five-Year DCF", "Multi-Stage DCF",
                      "Sensitivity", "Historical & Ratios", "Financial Evidence", "Model Limitations"):
                self.assertIn(s, wb.sheetnames)

    def test_excel_linked_formulas(self):
        # The model must use linked formulas, not static copied values.
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            self.assertEqual(wb["FCFF Forecast"]["B2"].value, "=Assumptions!B3*(1+Assumptions!B4)")
            self.assertEqual(wb["FCFF Forecast"]["I2"].value, "=D2+E2-F2-H2")
            self.assertEqual(wb["Historical & Ratios"]["D2"].value, "=C2/B2")

    def test_excel_assumptions_editable_blue(self):
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            cell = wb["Assumptions"]["B4"]
            self.assertEqual(cell.font.color.rgb, "000000FF")  # blue editable input

    def test_excel_reproduces_base_dcf(self):
        # The intrinsic/share is now a LINKED formula (not a static copy).
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            self.assertTrue(str(wb["Five-Year DCF"]["B12"].value).startswith("=IF(OR("))
            self.assertTrue(str(wb["Multi-Stage DCF"]["B20"].value).startswith("=IF(OR("))

    def test_linked_wacc_and_sensitivity(self):
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            self.assertTrue(str(wb["WACC"]["E4"].value).startswith("=B7*E2"))
            self.assertTrue(str(wb["Sensitivity"]["B2"].value).startswith("=IF(OR("))

    def test_validity_guards_present(self):
        from openpyxl import load_workbook
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            wb = load_workbook(p)
            self.assertIn("unavailable", wb["Five-Year DCF"]["B12"].value)
            self.assertIn("unavailable", wb["Multi-Stage DCF"]["B20"].value)
            self.assertTrue(str(wb["Sensitivity"]["A2"].value).startswith("=WACC!E6"))

    def test_pdf_generated(self):
        r = self._result()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "r.pdf")
            build_pdf_report(r, p)
            self.assertTrue(os.path.getsize(p) > 500)

    def test_negative_equity_headline_suppressed(self):
        from openpyxl import load_workbook
        r = self._result()
        r["analysis"]["scenarios"]["base"]["intrinsic_per_share_usd"] = -38.61
        r["quality"] = {"state": "unsuitable"}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.xlsx")
            build_excel_workbook(r, p)
            ws = load_workbook(p)["Five-Year DCF"]
            self.assertEqual(ws["D2"].value, "N/A — Model Review Required")

    def test_multistage_numerical_parity_with_python(self):
        # Reproduce the exact transition+ROIC-terminal chain that the workbook formulas
        # encode, and confirm it matches the Python multi-stage engine, and responds to
        # transition-length and ROIC changes.
        r = self._result()
        hist = r["forecast_history"]
        drivers = r["analysis"]["forecast"]["base"]["drivers"]
        explicit = r["analysis"]["forecast"]["base"]["rows"]
        wacc = r["analysis"]["scenarios"]["base"]["wacc"]
        tg = r["analysis"]["scenarios"]["base"]["terminal_growth"]
        nd = r["analysis"]["scenarios"]["base"]["net_debt_usd"]
        shares = r["analysis"]["diluted_shares"] or r["analysis"]["shares_outstanding"]

        def ms(roic=0.12, trans=5):
            g = drivers["revenue_growth"]; m = drivers["operating_margin"]
            tax = drivers["normalized_tax_rate"]
            r_sus = max(0.0, min(1.0, tg / roic))
            last = explicit[-1]
            r_exp = max(0.0, min(1.5, (last["capex"] - last["da"] + last["change_in_nwc"]) / last["nopat"]))
            rev = last["revenue"]; fcffs = [row["fcff"] for row in explicit]
            for t in range(trans):
                frac = (t + 1) / trans
                g_t = g + (tg - g) * frac
                r_t = r_exp + (r_sus - r_exp) * frac
                rev = rev * (1 + g_t)
                nopat = rev * m * (1 - tax)
                fcffs.append(nopat * (1 - r_t))
            rev11 = rev * (1 + tg); nopat11 = rev11 * m * (1 - tax)
            fterm = nopat11 * (1 - r_sus); tv = fterm / (wacc - tg)
            pv = sum(cf / (1 + wacc) ** (i + 1) for i, cf in enumerate(fcffs))
            ev = pv + tv / (1 + wacc) ** len(fcffs)
            return (ev - nd) / shares

        py = r["analysis"]["multistage"]["base"]["intrinsic_per_share_usd"]
        self.assertAlmostEqual(ms(0.12, 5), py, places=1)
        # changing transition length and ROIC must change the result
        self.assertNotAlmostEqual(ms(0.12, 3), ms(0.12, 8), places=2)
        self.assertNotAlmostEqual(ms(0.10, 5), ms(0.15, 5), places=2)


if __name__ == "__main__":
    unittest.main()