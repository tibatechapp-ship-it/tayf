"""In-memory sliding-window rate limiter — pure dependency, zero deps.

Why in-memory: the deployment target is a single uvicorn process (Termux /
small VPS). For multi-replica deployments swap the ``_STORE`` for Redis — the
dependency contract stays identical.

Applied to the bruteforce-sensitive routes:
  - POST /auth/register, /auth/login, /auth/refresh  -> bucket "auth"
  - POST /projects/{id}/jobs                          -> bucket "jobs"

Client identity: the direct peer address, unless that peer is listed in
``TRUSTED_PROXIES`` — only then is ``X-Forwarded-For`` consulted (rightmost
untrusted hop). An arbitrary caller cannot rotate the header to evade a limit.

Disable entirely with ``RATELIMIT_ENABLED=false`` (tests / trusted networks).
"""

from __future__ import annotations

import ipaddress
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


def _normalize_ip(value: str) -> str:
    """Strip an optional IPv6 port: ``[::1]:1234`` -> ``::1``."""
    value = value.strip()
    if value.startswith("["):
        return value[1:].split("]", 1)[0]
    return value


def _is_trusted(peer: str, trusted: list[str]) -> bool:
    """Whether *peer* is one of the configured trusted proxies."""
    candidate = _normalize_ip(peer)
    try:
        peer_ip = ipaddress.ip_address(candidate)
    except ValueError:
        # Non-IP peers (e.g. TestClient's "testclient") still match if listed.
        return candidate in trusted
    for entry in trusted:
        try:
            if peer_ip in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            if candidate == _normalize_ip(entry):
                return True
    return False


def _forwarded_client(forwarded: str, trusted: list[str]) -> str | None:
    """Rightmost untrusted XFF hop, or None when every hop is trusted."""
    for hop in reversed([h for h in forwarded.split(",") if h.strip()]):
        value = _normalize_ip(hop)
        try:
            ipaddress.ip_address(value)
        except ValueError:
            continue  # malformed hop: never let it become an identity
        if not _is_trusted(value, trusted):
            return value
    return None


def _client_identity(request: Request) -> str:
    """Real client behind a trusted proxy, otherwise the direct peer.

    ``X-Forwarded-For`` is caller-controlled: honoring it from an arbitrary
    peer would let anyone rotate the header and bypass the per-IP limit.
    """
    settings = get_settings()
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        trusted = settings.trusted_proxies_list
        if _is_trusted(peer, trusted):
            real_client = _forwarded_client(forwarded, trusted)
            if real_client is not None:
                return real_client
    return peer


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
