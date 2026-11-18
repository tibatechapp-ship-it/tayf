"""Neutral artifact references: keys in DB, fresh signed URLs at read time."""

from app.core.file_tokens import extract_signed_key, verify_file_token
from app.services.storage.base import StorageBackend, StorageError
from app.services.storage.factory import get_storage
from app.services.storage.refs import artifact_url, key_from_ref, sign_review

FILES_PREFIX = "/api/v1/files/"


def test_store_bytes_returns_neutral_key_not_url():
    storage = get_storage()
    key = storage.store_bytes("neutral/roundtrip.txt", b"neutral", "text/plain")
    assert key == "neutral/roundtrip.txt"
    assert storage.get_bytes(key) == b"neutral"

    signed = storage.signed_url(key, 120)
    assert signed.startswith(FILES_PREFIX)
    parsed_key, exp, sig = extract_signed_key(signed)
    assert parsed_key == key
    assert verify_file_token(parsed_key, exp, sig) is True
    storage.delete(key)


def test_key_from_ref_accepts_keys_local_urls_and_legacy_s3_urls(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "S3_BUCKET", "tayf-assets")

    assert key_from_ref("jobs/1/video.mp4") == "jobs/1/video.mp4"
    assert key_from_ref(f"{FILES_PREFIX}jobs/1/video.mp4?exp=10&sig=abc") == "jobs/1/video.mp4"
    assert key_from_ref("https://tayf-assets.s3.amazonaws.com/jobs/1/thumb.jpg?X-Amz-Signature=x") == "jobs/1/thumb.jpg"
    assert key_from_ref("https://s3.example.com/tayf-assets/jobs/1/clip.mp4?X-Amz-Signature=x") == "jobs/1/clip.mp4"
    assert key_from_ref("../etc/passwd") is None


def test_artifact_url_signs_key_and_legacy_url(client):
    storage = get_storage()
    key = storage.store_bytes("neutral/schema.txt", b"schema", "text/plain")

    fresh = artifact_url(key, ttl_seconds=120)
    legacy = artifact_url(f"{FILES_PREFIX}{key}", ttl_seconds=120)
    assert fresh and "exp=" in fresh and "sig=" in fresh
    assert legacy and "exp=" in legacy and "sig=" in legacy
    assert client.get(fresh).status_code == 200
    storage.delete(key)


def test_sign_review_refreshes_artifact_fields():
    review = {
        "kind": "images",
        "video_url": None,
        "thumbnail_url": "neutral/legacy-thumb.jpg",
        "scenes": [{"image_url": "neutral/scene_1.png", "description": "keep me"}],
    }
    signed = sign_review(review)
    assert signed["video_url"] is None
    assert str(signed["thumbnail_url"]).startswith(FILES_PREFIX)
    assert "sig=" in str(signed["thumbnail_url"])
    assert "sig=" in signed["scenes"][0]["image_url"]
    assert signed["scenes"][0]["description"] == "keep me"
    # the stored review dict is untouched
    assert review["scenes"][0]["image_url"] == "neutral/scene_1.png"


def test_custom_backend_inherits_neutral_url_wrapper():
    class DummyBackend(StorageBackend):
        name = "dummy"

        def store_bytes(self, key, data, content_type):
            return key

        def get_bytes(self, key):
            return b""

        def exists(self, key):
            return True

        def delete(self, key):
            return None

        def iter_keys(self, prefix=""):
            return []

        def key_modified_at(self, key):
            return None

        def url_for(self, key):
            return f"dummy://{key}"

    backend = DummyBackend()
    assert backend.put_bytes("k", b"x", "text/plain") == "dummy://k"
    assert backend.signed_url("k", 60) == "dummy://k"
    try:
        backend.local_path("k")
    except StorageError:
        pass
    else:
        raise AssertionError("local_path must be unsupported for non-local backends")
