"""Files route: serves local-storage artifacts (videos, thumbnails, keyframes).

For the S3 backend this redirects to a pre-signed URL instead. Path traversal
is blocked in the storage layer itself; the local path check here is a second
guard, not the only one.
"""

import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from app.services.storage.base import StorageError
from app.services.storage.factory import get_storage
from app.services.storage.local import LocalStorageBackend

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}", response_model=None)
def get_file(key: str) -> FileResponse | RedirectResponse:
    storage = get_storage()
    try:
        if isinstance(storage, LocalStorageBackend):
            path = (storage.base / key).resolve()
            if not str(path).startswith(str(storage.base)) or not path.is_file():
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="الملف غير موجود"
                )
            media_type = (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            return FileResponse(path, media_type=media_type)
        # S3 backend: hand the client a pre-signed URL
        return RedirectResponse(
            url=storage.url_for(key), status_code=status.HTTP_302_FOUND
        )
    except StorageError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="الملف غير موجود"
        ) from exc
