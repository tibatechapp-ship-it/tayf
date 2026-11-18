"""External moderation seam for prompt screening (T-20).

The local safety layer stays the first gate. When ``MODERATION_API_URL`` is
configured, this client sends the already-normalized text to an external
moderator and applies its verdict. The expected JSON response is::

    {"allowed": false, "category": "hate", "reason": "..."}

``flagged`` is accepted as the inverse of ``allowed``. Any transport error,
timeout, non-2xx status or malformed payload is fail-closed by default: the
prompt is rejected as ``moderation_unavailable``. Setting
``MODERATION_FAIL_CLOSED=false`` explicitly allows falling back to the local
term list when the external service is down.

No secret is stored here: the API key comes from configuration and is sent as
a Bearer token only when configured.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings

_UNAVAILABLE_REASON = "خدمة التدقيق الخارجية غير متاحة؛ لم يُسمح بالتوليد"
_EXTERNAL_REASON = "تم رفض الوصف وفق سياسة خدمة التدقيق الخارجية"


@dataclass(frozen=True)
class ModerationResult:
    allowed: bool
    category: str | None = None
    reason: str | None = None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ModerationClient:
    """Small synchronous HTTP client; safe to call from a worker thread."""

    def __init__(
        self,
        url: str,
        api_key: str = "",
        timeout_seconds: float = 5.0,
        fail_closed: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url.strip()
        self.timeout_seconds = timeout_seconds
        self.fail_closed = fail_closed
        self._transport = transport
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._headers = headers

    def check(self, text: str) -> ModerationResult:
        """Return the external verdict, or a fail-closed/fail-open fallback."""
        if not self.url:
            return ModerationResult(True)

        try:
            with httpx.Client(
                headers=self._headers,
                timeout=self.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.post(self.url, json={"text": text})
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f"moderator returned HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("moderator response must be a JSON object")

            if "allowed" in payload:
                allowed = payload["allowed"]
            elif "flagged" in payload:
                allowed = not payload["flagged"]
            else:
                raise ValueError("moderator response needs 'allowed' or 'flagged'")
            if not isinstance(allowed, bool):
                raise ValueError("moderator verdict must be boolean")

            if allowed:
                return ModerationResult(True)

            category = _clean_text(payload.get("category") or payload.get("label"))
            reason = _clean_text(payload.get("reason") or payload.get("message"))
            return ModerationResult(
                False,
                category or "external_moderation",
                reason or _EXTERNAL_REASON,
            )
        except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
            if self.fail_closed:
                return ModerationResult(False, "moderation_unavailable", _UNAVAILABLE_REASON)
            return ModerationResult(True)


def get_moderation_client() -> ModerationClient | None:
    """Build a client from settings; ``None`` means external moderation is off."""
    if not settings.MODERATION_API_URL.strip():
        return None
    return ModerationClient(
        url=settings.MODERATION_API_URL,
        api_key=settings.MODERATION_API_KEY,
        timeout_seconds=settings.MODERATION_TIMEOUT_SECONDS,
        fail_closed=settings.MODERATION_FAIL_CLOSED,
    )
