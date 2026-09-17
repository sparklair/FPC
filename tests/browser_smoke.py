"""Optional real-browser checks against a running local server.

Run: python tests/browser_smoke.py
Requires requirements-dev.txt and `python -m playwright install chromium`.
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    base = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5000")
    output = Path("test-results")
    output.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        options = {"headless": True}
        if os.getenv("CHROMIUM_PATH"):
            options["executable_path"] = os.environ["CHROMIUM_PATH"]
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        sockets = []
        page.on("websocket", lambda socket: sockets.append(socket.url))
        page.goto(base, wait_until="networkidle")
        page.wait_for_function("document.querySelector('#feed-status').textContent.includes('LIVE STREAM')")

        # Reset through the UI and verify the confirmation is required.
        page.locator("#reset-simulation").click()
        assert page.locator("#confirm-dialog").is_visible()
        page.locator("#confirm-action").click()
        page.wait_for_function("document.querySelector('#frame-count').textContent === '0'")
        page.wait_for_function("Number(document.querySelector('#frame-count').textContent) >= 2")
        assert sockets and any("transport=websocket" in url for url in sockets)
        assert page.evaluate("Chart.getChart('chart-0').data.datasets[0].data.length") >= 3
        assert page.evaluate("document.body.scrollWidth <= innerWidth")
        assert page.locator("#reset-simulation").bounding_box()["y"] < 1080
        page.screenshot(path=str(output / "dashboard-desktop.png"), full_page=True)

        # Pause freezes frames; chart switching remains interactive.
        page.locator("#pause-toggle").click()
        page.wait_for_function("document.querySelector('#simulation-status').textContent === 'PAUSED'")
        sequence = page.locator("#frame-count").inner_text()
        page.wait_for_timeout(1200)
        assert page.locator("#frame-count").inner_text() == sequence
        for group in ("thermal", "attitude", "computer", "power"):
            page.locator(f'[data-chart-group="{group}"]').click()
            assert page.evaluate("Chart.getChart('chart-0').data.datasets[0].data.length") >= 3

        # An operator command must be confirmed and change the actual spacecraft.
        page.locator("#execute-command").click()
        page.locator('[value="cancel"]').click()
        assert page.locator('[data-value="payload_status"]').inner_text() == "ON"
        page.locator("#execute-command").click()
        page.locator("#confirm-action").click()
        page.wait_for_function("document.querySelector('[data-value=payload_status]').textContent === 'OFF'")
        page.locator("#command-select").select_option("PAYLOAD_ON")
        page.locator("#execute-command").click()
        page.locator("#confirm-action").click()
        page.wait_for_function("document.querySelector('[data-value=payload_status]').textContent === 'ON'")

        # Warning -> critical -> automatic shutdown -> resolved incident.
        page.locator('[data-speed="2"]').click()
        page.locator('[data-fault="PAYLOAD_OVERHEAT"]').click()
        page.locator("#pause-toggle").click()
        page.wait_for_function("Number(document.querySelector('#alarm-count').textContent) > 0", timeout=25000)
        page.wait_for_function("document.querySelector('[data-value=payload_status]').textContent === 'OFF'", timeout=20000)
        page.screenshot(path=str(output / "payload-protection.png"), full_page=True)
        page.wait_for_function("document.querySelector('#incident-state').textContent === 'RESOLVED'", timeout=20000)
        assert page.locator("#alarm-count").inner_text() == "0"
        page.locator('[data-log="commands"]').click()
        assert "PAYLOAD_OFF" in page.locator("#journal-table").inner_text()
        page.locator('[data-log="incidents"]').click()
        page.locator("[data-incident-id]").first.click()
        assert "PAYLOAD_OFF" in page.locator("#incident-detail").inner_text()

        # Reconnect recovers history and state without REST polling.
        context.set_offline(True)
        page.wait_for_function("document.querySelector('#feed-status').textContent.includes('RECONNECTING')", timeout=30000)
        assert page.locator("#execute-command").is_disabled()
        context.set_offline(False)
        page.wait_for_function("document.querySelector('#feed-status').textContent.includes('LIVE STREAM')", timeout=15000)
        assert not page.locator("#execute-command").is_disabled()
        assert page.evaluate("Chart.getChart('chart-0').data.datasets[0].data.length") > 10

        # Auto-demo toggle, mobile layout, and clean final state.
        page.locator("#demo-toggle").click()
        page.wait_for_function("document.querySelector('#demo-toggle').getAttribute('aria-pressed') === 'true'")
        page.locator("#demo-toggle").click()
        page.wait_for_function("document.querySelector('#demo-toggle').getAttribute('aria-pressed') === 'false'")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.body.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "dashboard-mobile.png"), full_page=True)
        response = context.request.post(base + "/api/simulation", data={"action": "reset"})
        assert response.ok
        assert not errors, errors
        browser.close()
        print(json.dumps({"result": "PASS", "websocket": True, "javascript_errors": errors, "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    main()
