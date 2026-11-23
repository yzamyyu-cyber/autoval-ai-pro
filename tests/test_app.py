import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from autoval.pipeline import build_analysis

APP = Path(__file__).resolve().parents[1] / "app.py"


class WorkspaceTests(unittest.TestCase):
    def test_compare_loads_two_fixtures_without_saved_outputs(self):
        app = AppTest.from_file(APP, default_timeout=20).run()
        app.radio[0].set_value("Compare Companies").run()
        self.assertFalse(app.exception)
        table = app.table[0].value
        self.assertEqual(list(table.columns), ["DEMO", "DEMO2"])
        self.assertEqual(table.loc["Valuation gap (%)", "DEMO"], "-3.55%")
        self.assertEqual(table.loc["Price-implied FCFF growth", "DEMO"], "6.98%")

    def test_offline_demo_opens_and_reprices_without_changing_original_report(self):
        app = AppTest.from_file(APP, default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.report[0]["mode"], "demo")
        self.assertEqual(app.success[0].value, "Independent DCF check passed")
        self.assertEqual(self._what_if(app), 139.85)

        app.slider[0].set_value(1.0).run()
        self.assertFalse(app.exception)
        self.assertEqual(self._what_if(app), 122.62)
        original = app.session_state.report[0]["analysis"]["scenarios"]["base"]
        self.assertAlmostEqual(original["intrinsic_per_share_usd"], 139.85, places=2)
        self.assertEqual(original["wacc"], .10)

        self._button(app, "Load offline demo").click().run()
        self.assertEqual(self._what_if(app), 139.85)

    def test_market_expectations_reacts_to_a_hypothetical_price(self):
        app = AppTest.from_file(APP, default_timeout=20).run()
        self.assertFalse(app.exception)
        target = next(item for item in app.metric if item.label == "Target price per share")
        self.assertEqual(target.value, "$145.00")

        app.checkbox[0].check().run()
        next(field for field in app.number_input if field.label == "Target price (USD per share)").set_value(170.0).run()
        self.assertFalse(app.exception)
        target = next(item for item in app.metric if item.label == "Target price per share")
        self.assertEqual(target.value, "$170.00")
        self.assertTrue(any("Repriced at $170.00" in item.value for item in app.success))

    def test_failed_live_run_keeps_the_last_completed_report(self):
        with patch.dict(os.environ, {"SEC_USER_AGENT": "Test contact@example.com"}):
            app = AppTest.from_file(APP, default_timeout=20).run()
            last_run = app.session_state.report[0]["run_utc"]
            with patch("autoval.pipeline.build_analysis", side_effect=ValueError("fixture provider unavailable")) as build:
                app.text_input[0].set_value("HD")
                self._button(app, "Run live analysis").click().run()
                build.assert_called_once_with("HD", "live", "Test contact@example.com")
            self.assertFalse(app.exception)
            self.assertIn("fixture provider unavailable", app.error[0].value)
            self.assertEqual(app.session_state.report[0]["run_utc"], last_run)

    def test_live_report_renders_mapped_to_its_own_data_mode(self):
        result, prices = build_analysis("DEMO", "demo")
        result.update(mode="live", company="Fixture issuer", ticker="FICT")
        with patch.dict(os.environ, {"SEC_USER_AGENT": "Test contact@example.com"}):
            app = AppTest.from_file(APP, default_timeout=20).run()
            with patch("autoval.pipeline.build_analysis", return_value=(result, prices)):
                app.text_input[0].set_value("FICT")
                self._button(app, "Run live analysis").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.report[0]["mode"], "live")
        self.assertTrue(any("Fixture issuer" in item.value for item in app.markdown))

    def test_home_depot_shortcut_and_browser_sec_contact_without_configuration(self):
        report, prices = build_analysis()
        report.update(ticker="HD", company="Fixture issuer", mode="live")
        with patch.dict(os.environ, {"SEC_USER_AGENT": "AutoValStudentResearch your-school-email@example.edu"}):
            app = AppTest.from_file(APP, default_timeout=20).run()
            self._button(app, "Home Depot (HD)").click().run()
            self.assertEqual(app.text_input(key="live_ticker").value, "HD")
            self._button(app, "Run live analysis").click().run()
            self.assertIn("Enter your SEC contact email", app.warning[0].value)
            app.text_input(key="sec_contact_input").set_value("contact@example.com")
            with patch("autoval.pipeline.build_analysis", return_value=(report, prices)) as build:
                self._button(app, "Run live analysis").click().run()
                build.assert_called_once_with("HD", "live", "AutoVal AI Pro contact@example.com")
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state.report[0]["ticker"], "HD")

    def test_offline_capex_lab_updates_driver_valuation(self):
        app = AppTest.from_file(APP, default_timeout=20).run()
        base = next(item.value for item in app.metric if item.label == "CapEx lab base DCF / share")
        adjusted = next(item.value for item in app.metric if item.label == "CapEx-adjusted DCF / share")
        self.assertEqual((base, adjusted), ("$326.68", "$326.68"))
        setting = next(field for field in app.number_input if field.label == "CapEx as a percentage of revenue")
        setting.set_value(15.0).run()
        self.assertFalse(app.exception)
        adjusted = next(item.value for item in app.metric if item.label == "CapEx-adjusted DCF / share")
        self.assertEqual(adjusted, "$231.27")
        self.assertEqual(self._what_if(app), 139.85)

    @staticmethod
    def _button(app, label):
        return next(button for button in app.button if button.label == label)

    @staticmethod
    def _what_if(app):
        metric = next(item for item in app.metric if item.label == "What-if DCF / share")
        return float(metric.value.replace("$", "").replace(",", ""))
