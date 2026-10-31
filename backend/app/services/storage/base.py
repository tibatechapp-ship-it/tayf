"""Storage abstraction (T-06).

Two interchangeable backends selected by STORAGE_BACKEND:
- local: plain filesystem (Termux default), served by GET /api/v1/files/{key}
- s3:    any S3-compatible object store (MinIO locally, AWS/R2/DO remotely)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone


class StorageError(RuntimeError):
    pass


class StorageBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes under `key`, return a URL usable by the client."""

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
