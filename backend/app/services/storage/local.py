"""Local filesystem storage backend (Termux default)."""

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.storage.base import StorageBackend, StorageError, sanitize_key


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

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url_for(key)

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
        base_prefix = str(self.base)
        keys: list[str] = []
        for path in self.base.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self.base))
                if rel.startswith(prefix):
                    keys.append(rel)
        del base_prefix
        return sorted(keys)

    def key_modified_at(self, key: str) -> datetime | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    def url_for(self, key: str) -> str:
        sanitize_key(key)
        return f"/api/v1/files/{key}"
