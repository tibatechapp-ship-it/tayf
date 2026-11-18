"""Local filesystem storage backend (Termux default)."""

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.file_tokens import sign_file_url
from app.services.storage.base import StorageBackend, StorageError, sanitize_key

FILES_PREFIX = "/api/v1/files/"


class LocalStorageBackend(StorageBackend):
    name = "local"

    def __init__(self, base_dir: str | None = None) -> None:
        self.base = Path(base_dir or settings.LOCAL_STORAGE_DIR).expanduser().resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        key = sanitize_key(key)
        path = (self.base / key).resolve()
        if not str(path).startswith(str(self.base)):
            raise StorageError(f"key escapes storage root: {key!r}")
        return path

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def store_bytes(self, key: str, data: bytes, content_type: str) -> str:
        key = sanitize_key(key)
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"not found: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def iter_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        for path in self.base.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self.base))
                if rel.startswith(prefix):
                    keys.append(rel)
        return sorted(keys)

    def key_modified_at(self, key: str) -> datetime | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    def url_for(self, key: str) -> str:
        return f"{FILES_PREFIX}{sanitize_key(key)}"

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        return sign_file_url(self.url_for(key), ttl_seconds=ttl_seconds) or self.url_for(key)
