"""Cost dashboard: real ledger totals, per-stage timing and owner scoping."""

from __future__ import annotations

import time

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def _create_job(client, headers, project_id: str, prompt: str = "لوحة تكلفة") -> dict:
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


def test_cost_report_aggregates_stages_models_and_ledger(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id)
    job = _wait_terminal(client, headers, created["id"])
    assert job["status"] == "completed", job

    response = client.get("/api/v1/costs/me", headers=headers)
    assert response.status_code == 200, response.text
    report = response.json()

    assert report["attribution"] == "scene_generation"
    assert report["credits_charged"] == 2
    assert report["credits_refunded"] == 0
    assert report["credits_net"] == 2
    assert report["jobs_analyzed"] >= 1
    assert report["scenes_generated"] >= 2
    assert report["total_duration_ms"] >= 0

    stages = {row["stage"]: row for row in report["stages"]}
    assert "storyboard" in stages
    assert "keyframes" in stages
    assert "store" in stages
    assert stages["keyframes"]["credits"] == 2
    assert stages["store"]["credits"] == 0

    assert report["models"]
    assert report["models"][0]["model_version"] == "mock-1.0"
    assert report["recent_jobs"][0]["job_id"] == created["id"]
    assert report["recent_jobs"][0]["attributed_credits"] == 2


def test_cost_report_refunds_and_ignores_other_users(
    client, auth_headers, project_id, monkeypatch
):
    from app.core.config import get_settings
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "إلغاء وتكلفة")
    job = _wait_terminal(client, headers, created["id"])
    assert job["status"] == "completed", job

    monkeypatch.setattr(get_settings(), "EXTERNAL_JOB_WORKER", True)
    fresh = _create_job(client, headers, project_id, "إلغاء قبل التنفيذ")
    cancelled = client.post(f"/api/v1/jobs/{fresh['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text

    other = register_and_login(client, username="cost_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    other_project = client.post(
        "/api/v1/projects",
        json={"name": "other", "description": ""},
        headers=other_headers,
    ).json()["id"]
    _create_job(client, other_headers, other_project, "مهمة مستخدم آخر")

    report = client.get("/api/v1/costs/me", headers=headers).json()
    assert report["credits_refunded"] == 2
    assert report["credits_net"] == 2  # one completed job remains after the refund
    assert all(row["credits_charged"] >= 0 for row in report["recent_jobs"])
    assert report["jobs_analyzed"] == 2


def test_cost_report_requires_auth_and_validates_limit(client, auth_headers):
    assert client.get("/api/v1/costs/me").status_code == 401
    headers, _ = auth_headers
    assert client.get("/api/v1/costs/me?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/costs/me?limit=201", headers=headers).status_code == 422
