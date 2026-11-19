"""Pro export: SRT, project file and scene stills are owner-scoped and honest."""

from __future__ import annotations

import io
import json
import time
import zipfile

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def _create_job(client, headers, project_id: str, prompt: str = "لوحة تصدير") -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": prompt, "num_scenes": 2},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def _wait_terminal(client, headers, job_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline and job["status"] not in TERMINAL:
        time.sleep(0.25)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    return job


def _completed_job(client, headers, project_id):
    created = _create_job(client, headers, project_id)
    job = _wait_terminal(client, headers, created["id"])
    assert job["status"] == "completed", job
    return job


def test_export_srt_is_arabic_ready_and_timed(client, auth_headers, project_id):
    headers, _ = auth_headers
    job = _completed_job(client, headers, project_id)

    response = client.get(f"/api/v1/jobs/{job['id']}/export/srt", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-subrip")
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")  # BOM present for players
    assert "-->" in text
    assert "00:00:00,000" in text
    # Description text from the storyboard is present as cue content.
    assert any(scene["description"] in text for scene in job["scenes"])


def test_export_project_file_is_portable_and_honest(client, auth_headers, project_id):
    headers, _ = auth_headers
    job = _completed_job(client, headers, project_id)

    response = client.get(f"/api/v1/jobs/{job['id']}/export/project", headers=headers)
    assert response.status_code == 200, response.text
    manifest = json.loads(response.content.decode("utf-8"))
    assert manifest["format"] == "tayf-project"
    assert manifest["format_version"] == 1
    assert manifest["job"]["id"] == job["id"]
    assert manifest["job"]["prompt"] == job["prompt"]
    assert manifest["job"]["status"] == "completed"
    assert isinstance(manifest["job"]["simulated"], bool)
    assert len(manifest["storyboard"]["scenes"]) == 2
    # No signed URLs leak into the portable manifest — neutral keys only.
    for scene in manifest["storyboard"]["scenes"]:
        assert "://" not in str(scene["image_ref"])
    assert "honesty" in manifest


def test_export_stills_zip_contains_keyframes(client, auth_headers, project_id):
    headers, _ = auth_headers
    job = _completed_job(client, headers, project_id)

    response = client.get(f"/api/v1/jobs/{job['id']}/export/stills", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert any(n.startswith("scene_") for n in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["count"] >= 1


def test_export_requires_auth_and_owner_scope(client, auth_headers, project_id):
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    job = _completed_job(client, headers, project_id)

    # Unauthenticated request is rejected.
    assert client.get(f"/api/v1/jobs/{job['id']}/export/srt").status_code == 401

    # Another user cannot read this job's exports (no existence oracle).
    other = register_and_login(client, username="export_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    for kind in ("srt", "project", "stills"):
        resp = client.get(f"/api/v1/jobs/{job['id']}/export/{kind}", headers=other_headers)
        assert resp.status_code == 404, (kind, resp.text)
