"""In-memory sliding-window rate limiter — pure dependency, zero deps.

Why in-memory: the deployment target is a single uvicorn process (Termux /
small VPS). For multi-replica deployments swap the ``_STORE`` for Redis — the
dependency contract stays identical.

Applied to the bruteforce-sensitive routes:
  - POST /auth/register, /auth/login, /auth/refresh  -> bucket "auth"
  - POST /projects/{id}/jobs                          -> bucket "jobs"

Client identity: ``X-Forwarded-For`` first hop when present (behind a proxy),
otherwise the direct peer address.

Disable entirely with ``RATELIMIT_ENABLED=false`` (tests / trusted networks).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

# bucket -> identity -> deque[timestamps]
_STORE: dict[str, dict[str, deque[float]]] = defaultdict(lambda: defaultdict(deque))
_LOCK = threading.Lock()
_PRUNE_COUNTER = {"calls": 0}

# Bucket -> configured limit setting name (resolved at call time so tests and
# runtime .env changes take effect without a restart).
_BUCKETS: dict[str, str] = {
    "auth": "RATELIMIT_AUTH_LIMIT",
    "jobs": "RATELIMIT_JOB_LIMIT",
}


def _client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def reset_store() -> None:
    """Clear all windows (used by tests between scenarios)."""
    with _LOCK:
        _STORE.clear()
        _PRUNE_COUNTER["calls"] = 0


def rate_limit(bucket: str):
    """Build a FastAPI dependency enforcing ``limit`` requests per window."""
    limit_setting = _BUCKETS.get(bucket)
    if limit_setting is None:  # pragma: no cover - programmer error
        raise ValueError(f"unknown rate-limit bucket: {bucket}")

    def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.RATELIMIT_ENABLED:
            return
        limit = getattr(settings, limit_setting)
        window = max(settings.RATELIMIT_WINDOW_SECONDS, 1)
        identity = _client_identity(request)
        now = time.monotonic()

        with _LOCK:
            window_deque = _STORE[bucket][identity]
            cutoff = now - window
            while window_deque and window_deque[0] < cutoff:
                window_deque.popleft()
            if len(window_deque) >= limit:
                # oldest hit still inside the window -> when the slot frees up
                retry_after = max(1, int(window_deque[0] + window - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="محاولات كثيرة جدًا - حاول لاحقًا",
                    headers={"Retry-After": str(retry_after)},
                )
            window_deque.append(now)
            _PRUNE_COUNTER["calls"] += 1
            if _PRUNE_COUNTER["calls"] >= 512:
                _prune_locked(now, window * 4)

    return _dependency


def _prune_locked(now: float, max_age: float) -> None:
    """Occasional global sweep so idle identities don't leak memory."""
    cutoff = now - max_age
    for identities in _STORE.values():
        empty = []
        for identity, window_deque in identities.items():
            while window_deque and window_deque[0] < cutoff:
                window_deque.popleft()
            if not window_deque:
                empty.append(identity)
        for identity in empty:
            del identities[identity]
    _PRUNE_COUNTER["calls"] = 0


# Shared dependency instances (FastAPI treats distinct instances as distinct).
auth_rate_limit = rate_limit("auth")
job_rate_limit = rate_limit("jobs")
