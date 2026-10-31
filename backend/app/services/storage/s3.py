"""S3-compatible storage backend (MinIO locally, AWS S3/R2/DO remotely).

Requires S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY in .env.
Returned URLs are pre-signed GETs valid for STORAGE_TTL_DAYS (matching the
auto-cleanup TTL, so links never outlive their artifact).
"""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.storage.base import StorageBackend, StorageError, sanitize_key


class S3StorageBackend(StorageBackend):
    name = "s3"

    def __init__(self) -> None:
        if not settings.s3_configured:
            raise StorageError(
                "S3 backend selected but S3_ENDPOINT/S3_BUCKET/S3_ACCESS_KEY/S3_SECRET_KEY "
                "are not fully configured in .env"
            )
        try:
            import boto3  # lazy import: only needed for the S3 path
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise StorageError("boto3 is not installed - add it to requirements") from exc

        self._bucket = settings.S3_BUCKET
        self._ttl_days = max(settings.STORAGE_TTL_DAYS, 1)
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        key = sanitize_key(key)
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )
        return self.url_for(key)

    def get_bytes(self, key: str) -> bytes:
        key = sanitize_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:  # type: ignore[attr-defined]
            raise StorageError(f"not found: {key}") from exc
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=sanitize_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=sanitize_key(key))

    def iter_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix or ""):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def key_modified_at(self, key: str) -> datetime | None:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=sanitize_key(key))
        except Exception:
            return None
        modified = head.get("LastModified")
        if modified is None:
            return None
        if modified.tzinfo is None:  # boto3 usually returns tz-aware datetimes
            modified = modified.replace(tzinfo=timezone.utc)
        return modified

    def url_for(self, key: str) -> str:
        key = sanitize_key(key)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(timedelta(days=self._ttl_days).total_seconds()),
        )

    def cleanup_expired(self, ttl_days: int) -> int:
        """Batch version using S3 listing metadata (avoids N head calls)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        deleted = 0
        for key in self.iter_keys():
            modified = self.key_modified_at(key)
            if modified is not None and modified < cutoff:
                self.delete(key)
                deleted += 1
        return deleted
