"""Storage abstraction (T-06).

Two interchangeable backends selected by STORAGE_BACKEND:
- local: plain filesystem (Termux default), served by GET /api/v1/files/{key}
- s3:    any S3-compatible object store (MinIO locally, AWS/R2/DO remotely)

Callers persist neutral object keys, not provider URLs. ``signed_url`` mints a
fresh short-lived URL at read time for whichever backend is active.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path


class StorageError(RuntimeError):
    pass


class StorageBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def store_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes under `key` and return the neutral object key."""

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Compatibility wrapper: store bytes and return a usable URL."""
        return self.url_for(self.store_bytes(key, data, content_type))

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Load bytes stored under `key` (raises StorageError if missing)."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def iter_keys(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    def key_modified_at(self, key: str) -> datetime | None: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        """Fresh short-lived URL. Backends without signing return url_for()."""
        return self.url_for(key)

    def local_path(self, key: str) -> Path:
        """Filesystem path for direct serving; only the local backend has one."""
        raise StorageError(f"{self.name} backend has no local filesystem path")

    def cleanup_expired(self, ttl_days: int) -> int:
        """Delete artifacts older than ttl_days. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        deleted = 0
        for key in self.iter_keys():
            modified = self.key_modified_at(key)
            if modified is not None and modified < cutoff:
                self.delete(key)
                deleted += 1
        return deleted


def sanitize_key(key: str) -> str:
    """Reject path traversal and normalize separators."""
    key = (key or "").strip().lstrip("/")
    if not key or ".." in key.split("/") or "\\" in key:
        raise StorageError(f"illegal storage key: {key!r}")
    return key
