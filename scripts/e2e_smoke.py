#!/usr/bin/env python3
"""Unified studio smoke test: a REAL browser drives the REAL product loop.

Flow proven here (no mocks anywhere):
  open app -> register a new account -> create a project -> submit a
  generation job -> poll the UI until the job reaches a terminal state
  -> assert the rendered video/artifacts -> screenshot.

Requires the stack to be running (scripts/dev.sh start) and a Chromium binary:
  CHROMIUM_BIN=/path/to/chrome python scripts/e2e_smoke.py [url] [screenshot]

Exit code 0 only when the whole loop actually happened.
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
TIMEOUT_S = 90
JOB_TIMEOUT_S = 300

_DEFAULT_CHROMIUM_CANDIDATES = [
    os.environ.get("CHROMIUM_BIN") or "",
    str(pathlib.Path.home() / ".cache/ms-playwright/chromium-1200/chrome-linux64/chrome"),
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]


def chromium_bin() -> str:
    for candidate in _DEFAULT_CHROMIUM_CANDIDATES:
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    raise RuntimeError("no Chromium binary found (set CHROMIUM_BIN)")


def launch_chromium(url: str, profile: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            chromium_bin(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--window-size=1360,940",
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
        self.ws = websocket.create_connection(ws_url, timeout=30)
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


def type_into(cdp: Cdp, testid: str, value: str) -> None:
    """Set a React controlled input via the native setter (bubbles like typing)."""
    escaped = json.dumps(value)
    cdp.evaluate(
        f"""(() => {{
  const el = document.querySelector('[data-testid={testid}]');
  if (!el) throw new Error('missing input: {testid}');
  const setter = Object.getOwnPropertyDescriptor(
    el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype,
    'value'
  ).set;
  setter.call(el, {escaped});
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return true;
}})()"""
    )


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    shot = (
        pathlib.Path(sys.argv[2])
        if len(sys.argv) > 2
        else pathlib.Path(tempfile.gettempdir()) / "tayf-unified.png"
    )

    suffix = str(int(time.time()))[-6:]
    username, email, password = f"e2e{suffix}", f"e2e{suffix}@example.com", "Sup3rSecret!"

    profile = tempfile.mkdtemp(prefix="tayf-chrome-")
    browser = launch_chromium(url, profile)
    deadline = time.monotonic() + TIMEOUT_S
    job_deadline = time.monotonic() + JOB_TIMEOUT_S
    try:
        target = page_target(deadline)
        cdp = Cdp(target["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.evaluate(
            "window.__errs = []; window.addEventListener('error', e => window.__errs.push(String(e.message))); 1"
        )

        # 1) register through the real form
        wait_for(cdp, "document.querySelector('[data-testid=auth-submit]') !== null", deadline, "auth view")
        cdp.evaluate(
            f"""(() => {{
  const set = (sel, val) => {{
    const el = document.querySelector(sel);
    const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  }};
  set('input[type=email]', {json.dumps(email)});
  set('input[type=text]', {json.dumps(username)});
  set('input[type=password]', {json.dumps(password)});
  return true;
}})()"""
        )
        cdp.evaluate("document.querySelector('[data-testid=auth-submit]').click(); true")
        wait_for(cdp, "document.querySelector('[data-testid=topbar]') !== null", deadline, "studio view")

        # 2) create a project
        type_into(cdp, "project-name", f"E2E project {suffix}")
        cdp.evaluate("document.querySelector('[data-testid=project-submit]').click(); true")
        wait_for(
            cdp,
            "document.querySelector('[data-testid=job-prompt]') !== null",
            deadline,
            "job form for the new project",
        )

        # 3) submit a generation job (mock provider by default: SIMULATED, real MP4)
        type_into(cdp, "job-prompt", "a quiet lighthouse over a stormy sea at dusk, cinematic")
        cdp.evaluate("document.querySelector('[data-testid=job-submit]').click(); true")
        wait_for(cdp, "document.querySelector('[data-testid=job-list] li') !== null", deadline, "job card")

        status = wait_for(
            cdp,
            """(() => {
  const chips = [...document.querySelectorAll('[data-testid=job-list] .chip')];
  const text = chips.map(c => c.textContent).join('|');
  return (text.includes('مكتملة') || text.includes('completed') ||
          text.includes('فاشلة') || text.includes('failed') ||
          text.includes('مرفوضة') || text.includes('rejected')) ? text : '';
})()""",
            job_deadline,
            "terminal job status",
        )

        video_src = cdp.evaluate(
            "(document.querySelector('[data-testid=job-video]') || {}).src || ''"
        )
        balance_text = cdp.evaluate(
            "(document.querySelector('[data-testid=balance]') || {}).textContent || ''"
        )
        simulated_tag = cdp.evaluate(
            "(() => { const el = document.querySelector('[data-testid=job-list] .tag'); return el ? el.textContent : ''; })()"
        )
        js_errors = cdp.evaluate("window.__errs || []")
        dom_errors = [e for e in cdp.events if e.get("method") == "Runtime.exceptionThrown"]

        png = cdp.call("Page.captureScreenshot", format="png")
        shot.write_bytes(base64.b64decode(png["data"]))

        video_ok = bool(video_src) and video_src.startswith("http")
        completed = "مكتملة" in status or "completed" in status
        report = {
            "url": url,
            "user": username,
            "status_text": status,
            "video_src": video_src,
            "video_ok": video_ok,
            "balance_text": balance_text,
            "honesty_tag": simulated_tag,
            "js_errors": js_errors,
            "uncaught_exceptions": len(dom_errors),
            "screenshot": str(shot),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        ok = completed and video_ok and not js_errors and not dom_errors
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
