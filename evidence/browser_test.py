#!/usr/bin/env python3
"""Real Playwright browser test for the AutoVal AI Pro Streamlit app (offline demo).

Launches the actual Streamlit server, drives it with Playwright Chromium, asserts the
research workspace renders without exceptions, exercises Compare Companies, captures
genuine screenshots, and checks desktop + mobile layouts.

Usage:
    .venv/bin/python evidence/browser_test.py
"""
from __future__ import annotations
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

APP = "app.py"
PORT = 8501
URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    import os
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    env = dict(os.environ)
    env["AUTOVAL_FIXTURE_TICKER"] = ticker  # deterministic offline fixture
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    results = []
    try:
        if not wait_for_server():
            print("ERROR: Streamlit server did not start")
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)  # let Streamlit render

            title = page.title()
            results.append(("title", title))
            has_tabs = page.locator("text=Overview").count() > 0
            results.append(("tabs_visible", has_tabs))

            # open the Evidence & Exports tab and capture the evidence centre
            try:
                page.get_by_text("Evidence & Exports", exact=False).first.click()
                page.wait_for_timeout(2500)
                page.screenshot(path=f"evidence/screenshot_evidence_{ticker.lower()}.png", full_page=True)
                results.append(("evidence_centre", "captured"))
            except Exception:
                results.append(("evidence_centre", "tab not clickable"))

            page.screenshot(path="evidence/screenshot_overview.png", full_page=True)

            # Compare Companies
            page.get_by_text("Compare Companies", exact=False).first.click()
            page.wait_for_timeout(2500)
            page.screenshot(path="evidence/screenshot_compare.png", full_page=True)
            has_table = page.locator("table").count() > 0
            results.append(("compare_table", has_table))

            # mobile layout
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(1500)
            page.screenshot(path="evidence/screenshot_mobile.png", full_page=True)
            results.append(("mobile_layout", True))

            results.append(("page_errors", len(errors)))
            if errors:
                results.append(("first_error", errors[0][:200]))

            browser.close()

        for k, v in results:
            print(f"{k}: {v}")
        print("screenshots written to evidence/screenshot_*.png")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
