"""Signed artifact URLs — short-lived HMAC tokens for the /files route.

Threat model: generated artifacts (videos / keyframes / thumbnails) are
non-guessable UUID paths, but "non-guessable" is not "authorized". If a URL
leaks (logs, browser history, screenshots), anyone holding it could fetch the
file. Signing makes every artifact URL a capability token with an expiry,
derived from ``JWT_SECRET`` — leak the secret and everything falls back to
normal JWT auth anyway.

Wire format (appended to the storage URL):
    /api/v1/files/<key>?exp=<unix_seconds>&sig=<hex>

Signed payload is ``key:exp`` with HMAC-SHA256. Verification is constant-time.

``FILES_PUBLIC=true`` reverts to the old open-URL behaviour (public demos);
default is signed (secure by default).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlparse

from app.core.config import get_settings

DEFAULT_TTL_SECONDS = 6 * 60 * 60  # artifact URLs stay valid for 6 hours
_FILES_PREFIX = "/api/v1/files/"


def _secret() -> bytes:
    return get_settings().jwt_secret_effective.encode("utf-8")


def _signature(key: str, exp: int) -> str:
    payload = f"{key}:{exp}".encode("utf-8")
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:32]


def sign_file_url(url: str | None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str | None:
    """Append an ``exp``/``sig`` pair to a local files URL. Other URLs pass through."""
    if not url or not url.startswith(_FILES_PREFIX):
        return url
    key = url[len(_FILES_PREFIX) :]
    # Strip any previous signature before re-signing.
    if "?" in key:
        key = key.split("?", 1)[0]
    if not key:
        return url
    exp = int(time.time()) + max(ttl_seconds, 1)
    sep = "&" if "?" in url else "?"
    return f"{url.split('?', 1)[0]}{sep}exp={exp}&sig={_signature(key, exp)}"


def verify_file_token(key: str, exp_str: str | None, sig: str | None) -> bool:
    """Return True when exp is in the future and sig matches key:exp."""
    if not exp_str or not sig:
        return False
    try:
        exp = int(exp_str)
    except (TypeError, ValueError):
        return False
    if exp < int(time.time()):
        return False
    expected = _signature(key, exp)
    return hmac.compare_digest(expected, sig)


def extract_signed_key(url: str) -> tuple[str, str | None, str | None]:
    """Split a files URL into (key, exp, sig) using the configured API prefix."""
    parsed = urlparse(url)
    path = parsed.path
    if not path.startswith(_FILES_PREFIX):
        return path, None, None
    key = path[len(_FILES_PREFIX) :]
    params = parse_qs(parsed.query)
    return key, (params.get("exp") or [None])[0], (params.get("sig") or [None])[0]
