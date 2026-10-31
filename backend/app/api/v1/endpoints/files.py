"""Files route: serves local-storage artifacts (videos, thumbnails, keyframes).

Access model (local backend): every URL carries a short-lived HMAC signature
(`?exp=...&sig=...`, minted by the API when it serializes job payloads). URLs
without a valid signature are rejected with 403 — “non-guessable UUID” alone
is not an authorization check. Set ``FILES_PUBLIC=true`` to serve artifacts
openly (public demos). For the S3 backend the route redirects to a pre-signed
object URL, which carries S3's own signature.

Path traversal is blocked in the storage layer itself; the local path check
here is a second guard, not the only one.
"""

import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from app.core.config import get_settings
from app.core.file_tokens import verify_file_token
from app.services.storage.base import StorageError
from app.services.storage.factory import get_storage
from app.services.storage.local import LocalStorageBackend

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}", response_model=None)
def get_file(key: str, exp: str | None = None, sig: str | None = None) -> FileResponse | RedirectResponse:
    storage = get_storage()
    local = isinstance(storage, LocalStorageBackend)
    # Signature enforcement only applies to the local backend (S3 pre-signs).
    if local and not get_settings().FILES_PUBLIC:
        if not verify_file_token(key, exp, sig):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="رابط الملف غير موقّع أو منتهي الصلاحية - اطلب الرابط من الواجهة من جديد",
            )
    try:
        if local:
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
