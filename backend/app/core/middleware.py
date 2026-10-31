"""Production-grade middleware, dependency-free — implemented as PURE ASGI.

Why pure ASGI instead of BaseHTTPMiddleware: zero task-spawning overhead and
no known deadlocks with streaming responses or TestClient — important for the
Termux/low-resource deployment target.

- SecurityHeadersMiddleware: hardens every response (nosniff, frame-deny,
  referrer policy, restrictive permissions policy).
- RequestIDMiddleware: propagates or generates X-Request-ID on every response
  and emits one structured access-log line per request.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("tayf.access")

# Only accept client-supplied request IDs that are safe to echo back.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SecurityHeadersMiddleware:
    """Defensive headers on every response (docs, API, files)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestIDMiddleware:
    """X-Request-ID propagation + one access-log line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw = ""
        for key, value in scope.get("headers") or []:
            if key == b"x-request-id":
                raw = value.decode("latin-1").strip()
                break
        request_id = raw if _SAFE_REQUEST_ID.match(raw) else uuid.uuid4().hex

        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %d (%.1f ms) request_id=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_holder["status"],
                duration_ms,
                request_id,
            )
