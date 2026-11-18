"""Provider-neutral artifact references.

The database stores *keys* (or legacy URLs), never provider-specific signed
URLs. This module converts any stored reference into a fresh short-lived URL
at read time, so clients see one stable contract whether the active backend is
local disk, MinIO, AWS S3, R2, or another S3-compatible store.
"""

from urllib.parse import unquote, urlparse

from app.core.config import get_settings
from app.services.storage.base import sanitize_key
from app.services.storage.factory import get_storage

FILES_PREFIX = "/api/v1/files/"


def key_from_ref(ref: str | None) -> str | None:
    """Extract a sanitized object key from a key, local URL, or legacy S3 URL."""
    if not ref:
        return None
    value = str(ref).strip()
    if not value:
        return None

    if value.startswith(FILES_PREFIX):
        raw_key = value[len(FILES_PREFIX) :].split("?", 1)[0]
    elif "://" in value:
        parsed = urlparse(value)
        raw_key = parsed.path.lstrip("/")
        bucket = get_settings().S3_BUCKET.strip().strip("/")
        # Path-style S3 URLs embed the bucket before the object key.
        if bucket and raw_key.startswith(f"{bucket}/"):
            raw_key = raw_key[len(bucket) + 1 :]
        # Virtual-hosted URLs (bucket.host/path) already start with the key.
    else:
        raw_key = value

    try:
        return sanitize_key(unquote(raw_key))
    except Exception:
        return None


def artifact_url(ref: str | None, ttl_seconds: int | None = None) -> str | None:
    """Return a fresh signed URL for a stored artifact reference."""
    key = key_from_ref(ref)
    if key is None:
        return None
    ttl = ttl_seconds or get_settings().STORAGE_SIGNED_URL_TTL_SECONDS
    return get_storage().signed_url(key, ttl)


def sign_review(review: object) -> object:
    """Refresh artifact URLs inside an approval review payload."""
    if not isinstance(review, dict):
        return review
    result = dict(review)
    for field in ("video_url", "thumbnail_url", "image_url"):
        if field in result:
            result[field] = artifact_url(result[field])
    scenes = result.get("scenes")
    if isinstance(scenes, list):
        result["scenes"] = [
            {**scene, "image_url": artifact_url(scene.get("image_url"))} if isinstance(scene, dict) else scene
            for scene in scenes
        ]
    return result
