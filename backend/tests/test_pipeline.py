"""End-to-end generation pipeline test with the Mock provider (real ffmpeg).

This is the acceptance test for the full product loop:
register -> login -> project -> job -> (storyboard -> keyframes -> compose)
-> completed with a real playable MP4 stored via the storage backend.

With Starlette BackgroundTasks the pipeline finishes BEFORE the 202 response
is observed by the test client, so no polling flakiness is possible here.
"""

import time


def _wait_for_terminal(client, headers, job_id, timeout_s=180) -> dict:
    deadline = time.time() + timeout_s
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("completed", "failed", "rejected"):
            return job
        time.sleep(1.0)
    return job


def test_full_text_to_video_pipeline_mock(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "golden gate bridge in fog at sunrise", "num_scenes": 2, "aspect": "16:9"},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job = created.json()
    assert job["status"] in ("pending", "processing", "completed")
    assert isinstance(job["simulated"], bool)

    job = _wait_for_terminal(client, headers, job["id"])
    assert job["status"] == "completed", job
    assert job["provider"] == "mock"
    assert job["model_version"] == "mock-1.0"
    assert job["simulated"] is True  # honesty flag on the terminal record

    # real artifacts
    assert job["output_url"] and job["output_url"].startswith("/api/v1/files/jobs/")
    assert (job["video_size_bytes"] or 0) > 10_000
    assert (job["duration_seconds"] or 0) > 2.0
    assert job["thumbnail_url"]

    # storyboard scenes with stored keyframes
    assert len(job["scenes"]) == 2
    for scene in job["scenes"]:
        assert scene["image_url"], scene

    # the video is actually fetchable and looks like an MP4
    video = client.get(job["output_url"])
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert video.content[4:8] == b"ftyp"  # ISO-BMFF signature

    thumb = client.get(job["thumbnail_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"

    # job list shows the completed job
    listing = client.get(f"/api/v1/projects/{project_id}/jobs", headers=headers)
    assert listing.status_code == 200
    assert any(
        j["id"] == job["id"] and j["status"] == "completed" for j in listing.json()
    )


def test_failed_job_refunds_credits(client, auth_headers, project_id, monkeypatch):
    headers, _ = auth_headers

    import app.services.pipeline as pipeline_module

    def boom():
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(pipeline_module, "get_ai_provider", boom)

    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "this will fail", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job = _wait_for_terminal(client, headers, created.json()["id"])

    assert job["status"] == "failed"
    assert "provider exploded" in (job["error_message"] or "")
    balance = client.get("/api/v1/credits/me", headers=headers).json()
    assert balance["balance"] == 100  # full refund: 100 - 2 + 2
    reasons = [entry["reason"] for entry in balance["entries"]]
    assert "refund_job_failed" in reasons


def test_jobs_are_owner_scoped(client, auth_headers, project_id):
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "private scene", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    other = register_and_login(client, username="job_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get(f"/api/v1/jobs/{job_id}", headers=other_headers).status_code == 404
    assert (
        client.get(f"/api/v1/projects/{project_id}/jobs", headers=other_headers).status_code
        == 404
    )
    # the owner still sees it
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers).status_code == 200
