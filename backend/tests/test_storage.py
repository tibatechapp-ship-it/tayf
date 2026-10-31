"""Storage + cleanup + files route tests (T-06)."""

import os
import time

from app.core.config import get_settings
from app.core.file_tokens import sign_file_url
from app.services.storage.factory import get_storage, run_cleanup_once
from app.services.storage.base import StorageError


def test_local_roundtrip_and_url():
    storage = get_storage()
    url = storage.put_bytes("tests/hello.txt", b"visionforge", "text/plain")
    assert url == "/api/v1/files/tests/hello.txt"
    assert storage.exists("tests/hello.txt")
    assert storage.get_bytes("tests/hello.txt") == b"visionforge"
    assert "tests/hello.txt" in storage.iter_keys()
    storage.delete("tests/hello.txt")
    assert not storage.exists("tests/hello.txt")


def test_path_traversal_blocked():
    storage = get_storage()
    for bad in ("../etc/passwd", "a/../../b", "", "a\\b"):
        try:
            storage.put_bytes(bad, b"x", "text/plain")
            raised = False
        except StorageError:
            raised = True
        assert raised, f"expected StorageError for {bad!r}"


def test_ttl_cleanup_deletes_only_old_files():
    storage = get_storage()
    old_key = "cleanup/old.txt"
    new_key = "cleanup/new.txt"
    storage.put_bytes(old_key, b"old", "text/plain")
    storage.put_bytes(new_key, b"new", "text/plain")

    old_time = time.time() - (get_settings().STORAGE_TTL_DAYS + 2) * 86400
    os.utime(str(storage.base / old_key), (old_time, old_time))

    deleted = run_cleanup_once()
    assert deleted >= 1
    assert not storage.exists(old_key)
    assert storage.exists(new_key)


def test_files_route_serves_stored_artifact(client):
    storage = get_storage()
    storage.put_bytes("routes/ping.txt", b"pong", "text/plain")
    signed = sign_file_url("/api/v1/files/routes/ping.txt")
    response = client.get(signed)
    assert response.status_code == 200
    assert response.text == "pong"


def test_files_route_missing_404(client):
    signed = sign_file_url("/api/v1/files/routes/does-not-exist.bin")
    assert client.get(signed).status_code == 404


def test_files_route_blocks_traversal(client):
    assert client.get("/api/v1/files/../secrets.txt").status_code in (400, 403, 404)


def test_s3_backend_requires_full_config(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "S3_ENDPOINT", "")
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "s3")
    try:
        get_storage()
        raised = False
    except (StorageError, ValueError):
        raised = True
    assert raised
