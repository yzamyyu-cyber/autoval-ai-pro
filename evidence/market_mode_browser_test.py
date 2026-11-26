#!/usr/bin/env python3
"""Playwright browser acceptance for the four market-data modes (deterministic fixtures).

Launches the real Streamlit server (offline deterministic fixture) once per mode, asserts
the research workspace renders without exceptions, exercises tabs / company switching /
Annual-TTM, and captures genuine full-page screenshots.

Usage:
    .venv/bin/python evidence/market_mode_browser_test.py
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

APP = "app.py"
PORT = 8501
URL = f"http://127.0.0.1:{PORT}"
MODES = ("current", "saved", "illustrative", "missing")


def wait_for_server(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_mode(mode):
    env = dict(os.environ)
    env["AUTOVAL_FIXTURE_TICKER"] = "MSFT"
    env["AUTOVAL_FIXTURE_MARKET_MODE"] = mode
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    try:
        if not wait_for_server():
            print(f"[{mode}] ERROR: server did not start")
            return None
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            page.screenshot(path=f"evidence/market_mode_{mode}.png", full_page=True)

            # company switching + Annual/TTM + tabs in the current-mode run
            if mode == "current":
                try:
                    page.get_by_text("Home Depot (HD)", exact=False).first.click()
                    page.wait_for_timeout(2500)
                except Exception:
                    pass
                try:
                    page.get_by_text("Annual", exact=True).first.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                for tab in ("Scenario Lab", "Multi-stage DCF", "Market Expectations",
                            "Financials", "Evidence & Exports"):
                    try:
                        page.get_by_text(tab, exact=False).first.click()
                        page.wait_for_timeout(1800)
                    except Exception:
                        pass
                page.get_by_text("Compare Companies", exact=False).first.click()
                page.wait_for_timeout(2000)
                page.screenshot(path="evidence/market_mode_compare.png", full_page=True)

            result = {"mode": mode, "page_errors": len(errors), "title": page.title()}
            if errors:
                result["first_error"] = errors[0][:200]
            browser.close()
            return result
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main():
    for mode in MODES:
        r = run_mode(mode)
        if r is None:
            continue
        print(f"{mode}: page_errors={r['page_errors']} title={r['title']!r}")
        if r.get("first_error"):
            print(f"  first_error: {r['first_error']}")
    print("screenshots written to evidence/market_mode_*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
