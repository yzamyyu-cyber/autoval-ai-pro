#!/usr/bin/env python3
"""Playwright browser acceptance for the AI Financial Reconciliation interface.

Launches the real Streamlit app with a deterministic fixture that carries a reconciliation
issue (stale nonzero short-term borrowings + restricted-cash scope), opens the Evidence &
Exports tab, and captures a genuine screenshot of the agent interface.

Usage:
    .venv/bin/python evidence/reconciliation_browser_test.py
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
    env = dict(os.environ)
    env["AUTOVAL_FIXTURE_TICKER"] = "MSFT"
    env["AUTOVAL_FIXTURE_RECON_ISSUE"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP,
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    try:
        if not wait_for_server():
            print("ERROR: server did not start")
            return 1
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            page.get_by_text("Evidence & Exports", exact=False).first.click()
            page.wait_for_timeout(2500)
            page.screenshot(path="evidence/reconciliation_interface.png", full_page=True)
            has_recon = page.get_by_text("AI Financial Reconciliation", exact=False).count() > 0
            has_issue = page.get_by_text("Detected issue", exact=False).count() > 0
            print(f"reconciliation_section: {has_recon}")
            print(f"detected_issue_rendered: {has_issue}")
            print(f"page_errors: {len(errors)}")
            if errors:
                print(f"first_error: {errors[0][:200]}")
            browser.close()
        print("screenshot written to evidence/reconciliation_interface.png")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
