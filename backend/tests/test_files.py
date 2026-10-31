"""Files route: content types, signed-URL enforcement + traversal rejection."""

import time

from fastapi.testclient import TestClient

from app.core.file_tokens import extract_signed_key, sign_file_url, verify_file_token
from app.services.storage.factory import get_storage


def test_files_serve_correct_content_types(client: TestClient):
    storage = get_storage()

    png = storage.put_bytes("route_tests/pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")
    mp4 = storage.put_bytes("route_tests/clip.mp4", b"\x00\x00\x00 ftypisom" + b"0" * 64, "video/mp4")

    response = client.get(sign_file_url(png))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    response = client.get(sign_file_url(mp4))
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"

    signed_missing = sign_file_url("/api/v1/files/route_tests/nope.png")
    assert client.get(signed_missing).status_code == 404

    # traversal never escapes the storage root
    traversed = client.get("/api/v1/files/../secret.txt")
    assert traversed.status_code in (400, 403, 404)


def test_unsigned_file_url_rejected(client):
    storage = get_storage()
    png = storage.put_bytes("route_tests/locked.png", b"\x89PNG\r\n\x1a\n" + b"1" * 64, "image/png")
    assert png.startswith("/api/v1/files/")

    # no signature -> 403 (capability required, not just a guessable UUID)
    assert client.get(png).status_code == 403
    # garbage signature -> 403
    assert client.get(f"{png}?exp=9999999999&sig=deadbeef").status_code == 403


def test_signed_url_roundtrip_and_expiry_window(client):
    storage = get_storage()
    png = storage.put_bytes("route_tests/signed.png", b"\x89PNG\r\n\x1a\n" + b"2" * 64, "image/png")
    signed = sign_file_url(png, ttl_seconds=60)
    assert "exp=" in signed and "sig=" in signed
    key, exp, sig = extract_signed_key(signed)
    assert verify_file_token(key, exp, sig) is True
    assert client.get(signed).status_code == 200
    # an expired token fails verification
    assert verify_file_token(key, "1", sig) is False


def test_files_serve_keyframes_from_a_completed_job(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "waterfall in a green valley", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    deadline = time.time() + 180
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline and job["status"] not in ("completed", "failed"):
        time.sleep(1.0)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "completed", job

    for scene in job["scenes"]:
        response = client.get(scene["image_url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
