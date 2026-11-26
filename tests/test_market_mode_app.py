"""AppTest acceptance for the four market-data modes (offline, deterministic).

Exercises the real Streamlit app with the deterministic fixture harness across
current / saved / illustrative / missing modes, asserting price display, reverse-DCF
gating and the market-data-mode surfacing.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def _app(market_mode):
    env = {"AUTOVAL_FIXTURE_TICKER": "MSFT", "AUTOVAL_FIXTURE_MARKET_MODE": market_mode}
    with patch.dict(os.environ, env):
        return AppTest.from_file(APP, default_timeout=40).run()


def _markdown(app):
    return "\n".join(str(m.value) for m in app.markdown)


class MarketModeAppTests(unittest.TestCase):
    def test_current_renders_price_and_reverse_dcf(self):
        app = _app("current")
        self.assertFalse(app.exception)
        self.assertIn("$533.16", _markdown(app))  # genuine close displayed
        self.assertTrue(any(m.label == "Implied annual FCFF growth" for m in app.metric))

    def test_saved_renders_dated_price_and_reverse_dcf(self):
        app = _app("saved")
        self.assertFalse(app.exception)
        self.assertIn("$533.16", _markdown(app))
        self.assertTrue(any(m.label == "Implied annual FCFF growth" for m in app.metric))

    def test_illustrative_shows_no_genuine_price_and_gates_reverse_dcf(self):
        app = _app("illustrative")
        self.assertFalse(app.exception)
        self.assertTrue(any("Reverse DCF is unavailable" in i.value for i in app.info))
        self.assertFalse(any(m.label == "Implied annual FCFF growth" for m in app.metric))

    def test_missing_shows_no_genuine_price_and_gates_reverse_dcf(self):
        app = _app("missing")
        self.assertFalse(app.exception)
        self.assertTrue(any("Reverse DCF is unavailable" in i.value for i in app.info))
        self.assertFalse(any(m.label == "Implied annual FCFF growth" for m in app.metric))

    def test_all_modes_no_unhandled_exception(self):
        for mode in ("current", "saved", "illustrative", "missing"):
            with self.subTest(mode=mode):
                self.assertFalse(_app(mode).exception)


if __name__ == "__main__":
    unittest.main()
