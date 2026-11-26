#!/usr/bin/env python3
"""Phase 7 — release-candidate browser screenshots (deterministic fixture)."""
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
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP, "--server.headless", "true",
         "--server.port", str(PORT), "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
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
            page.screenshot(path="evidence/screenshot_overview.png", full_page=True)
            for tab, fname in (("Multi-stage DCF", "screenshot_multistage.png"),
                               ("AI Research Analyst", "screenshot_research.png"),
                               ("Evidence & Exports", "screenshot_evidence.png"),
                               ("Industry & Peers", "screenshot_peers.png"),
                               ("Market Data", "screenshot_market_data.png"),
                               ("AI Reconciliation", "screenshot_reconciliation.png")):
                try:
                    page.get_by_text(tab, exact=False).first.click()
                    page.wait_for_timeout(1800)
                    page.screenshot(path=f"evidence/{fname}", full_page=True)
                except Exception:
                    pass
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(1500)
            page.screenshot(path="evidence/screenshot_mobile.png", full_page=True)
            print(f"page_errors: {len(errors)}")
            if errors:
                print("first_error:", errors[0][:200])
            browser.close()
        print("screenshots written to evidence/screenshot_*.png")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
