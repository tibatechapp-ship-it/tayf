"""Storage backend factory + TTL cleanup entry point."""

from app.core.config import settings
from app.services.storage.base import StorageBackend


def get_storage() -> StorageBackend:
    backend = settings.STORAGE_BACKEND.strip().lower()
    if backend == "local":
        from app.services.storage.local import LocalStorageBackend

        return LocalStorageBackend()
    if backend == "s3":
        from app.services.storage.s3 import S3StorageBackend

        return S3StorageBackend()
    raise ValueError(f"Unknown STORAGE_BACKEND='{backend}'. Expected: local | s3")


def run_cleanup_once(backend: StorageBackend | None = None) -> int:
    """Delete artifacts older than STORAGE_TTL_DAYS. Returns deleted count."""
    storage = backend or get_storage()
    return storage.cleanup_expired(settings.STORAGE_TTL_DAYS)
