#!/usr/bin/env python3
"""Stage-1 smoke test: proves frontend -> Vite proxy -> FastAPI in a real browser.

Usage (servers already running):
    python scripts/e2e_smoke.py http://127.0.0.1:5173

Exit code 0 only when the button click produced a successful health response.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import websocket  # websocket-client

CDP_PORT = 9223
TIMEOUT_S = 45


def launch_chromium(url: str, profile: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "chromium-browser",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--window-size=1280,900",
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile}",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def page_target(deadline: float) -> dict:
    import urllib.request

    last = "no attempt"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2) as resp:
                targets = json.load(resp)
            pages = [t for t in targets if t.get("type") == "page" and str(t.get("url")).startswith("http")]
            if pages:
                return pages[0]
            last = f"targets={[t.get('type') for t in targets]}"
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.4)
    raise RuntimeError(f"no page target (last observed: {last})")


class Cdp:
    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self.next_id = 0
        self.events: list[dict] = []

    def call(self, method: str, **params) -> dict:
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.next_id:
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")


def wait_for(cdp: Cdp, expression: str, deadline: float, label: str):
    while time.monotonic() < deadline:
        value = cdp.evaluate(expression)
        if value:
            return value
        time.sleep(0.3)
    raise RuntimeError(f"timed out waiting for {label}")


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    shot = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(tempfile.gettempdir()) / "tayf-stage1.png"

    profile = tempfile.mkdtemp(prefix="vf-chrome-")
    browser = launch_chromium(url, profile)
    deadline = time.monotonic() + TIMEOUT_S
    try:
        target = page_target(deadline)
        cdp = Cdp(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.evaluate("window.__errs = []; window.addEventListener('error', e => window.__errs.push(String(e.message))); 1")

        wait_for(cdp, "document.querySelector('[data-testid=check-server]') !== null", deadline, "React mount")
        initial = cdp.evaluate("document.querySelector('[data-testid=health-status]').textContent")
        cdp.evaluate("document.querySelector('[data-testid=check-server]').click(); true")

        status_text = wait_for(
            cdp,
            "(() => { const t = document.querySelector('[data-testid=health-status]').textContent || '';"
            " return (t.includes('ناجح') || t.includes('succeeded') || t.includes('فشل') || t.includes('failed')) ? t : ''; })()",
            deadline,
            "health check result",
        )
        payload_text = cdp.evaluate("(document.querySelector('[data-testid=health-json]') || {}).textContent || ''")
        js_errors = cdp.evaluate("window.__errs || []")
        dom_errors = [e for e in cdp.events if e.get("method") == "Runtime.exceptionThrown"]

        png = cdp.call("Page.captureScreenshot", format="png")
        shot.write_bytes(base64.b64decode(png["data"]))

        payload = json.loads(payload_text) if payload_text else {}
        report = {
            "url": url,
            "initial_status_text": initial,
            "status_text": status_text,
            "payload": payload,
            "js_errors": js_errors,
            "uncaught_exceptions": len(dom_errors),
            "screenshot": str(shot),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        ok = (
            payload.get("status") == "ok"
            and payload.get("service") == "tayf-backend"
            and not js_errors
            and not dom_errors
            and ("ناجح" in status_text or "succeeded" in status_text)
        )
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()


if __name__ == "__main__":
    sys.exit(main())
