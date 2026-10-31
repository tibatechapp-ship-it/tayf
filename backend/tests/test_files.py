"""Files route: content types + traversal rejection at the HTTP boundary."""

import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.storage.factory import get_storage


def test_files_serve_correct_content_types(client: TestClient):
    storage = get_storage()
    settings = get_settings()

    png = storage.put_bytes("route_tests/pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")
    mp4 = storage.put_bytes("route_tests/clip.mp4", b"\x00\x00\x00 ftypisom" + b"0" * 64, "video/mp4")

    response = client.get(png)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    response = client.get(mp4)
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"

    missing = client.get("/api/v1/files/route_tests/nope.png")
    assert missing.status_code == 404

    # traversal never escapes the storage root
    traversed = client.get("/api/v1/files/../secret.txt")
    assert traversed.status_code in (400, 404)

    _ = settings  # settings import kept meaningful for auth-on-files decisions


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
