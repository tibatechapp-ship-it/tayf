"""Live job progress: signed stream tickets and SSE event frames."""

from __future__ import annotations

import time
import uuid
from urllib.parse import quote

from app.core.stream_tickets import issue_stream_ticket, verify_stream_ticket

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def _create_job(client, headers, project_id: str, prompt: str) -> dict:
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


def _ticket(client, headers, job_id: str):
    response = client.post(f"/api/v1/jobs/{job_id}/stream-ticket", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_job_exposes_progress_fields(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "مشهد مع تقدم حي")
    job = _wait_terminal(client, headers, created["id"])
    assert job["status"] == "completed", job
    assert job["progress"] == 100
    assert job["stage"] == "completed"


def test_stream_ticket_requires_auth(client, auth_headers, project_id):
    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "تذكرة بدون توكن")
    assert client.post(f"/api/v1/jobs/{job['id']}/stream-ticket").status_code == 401


def test_stream_ticket_is_owner_scoped(client, auth_headers, project_id):
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "مهمة خاصة")
    other = register_and_login(client, username="stream_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    response = client.post(f"/api/v1/jobs/{job['id']}/stream-ticket", headers=other_headers)
    assert response.status_code == 404


def test_sse_emits_progress_and_done(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "بث مباشر للتقدم")
    job = _wait_terminal(client, headers, created["id"])
    ticket = _ticket(client, headers, job["id"])
    assert ticket["job_id"] == job["id"]
    assert ticket["expires_in"] == 300

    url = f"/api/v1/jobs/{job['id']}/events?ticket={quote(ticket['ticket'])}"
    with client.stream("GET", url) as response:
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b"".join(response.iter_bytes()).decode("utf-8")

    assert "event: progress" in body
    assert "event: done" in body
    assert job["id"] in body
    assert '"stage":"completed"' in body
    assert '"progress":100' in body


def test_sse_rejects_invalid_expired_and_mismatched_tickets(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "تذاكر مرفوضة")
    job = _wait_terminal(client, headers, created["id"])

    bad = client.get(f"/api/v1/jobs/{job['id']}/events?ticket=not-a-ticket")
    assert bad.status_code == 401

    expired, _, _ = issue_stream_ticket(
        uuid.uuid4(), uuid.UUID(job["id"]), ttl_seconds=-1
    )
    assert (
        client.get(f"/api/v1/jobs/{job['id']}/events?ticket={quote(expired)}").status_code
        == 401
    )

    ticket = _ticket(client, headers, job["id"])["ticket"]
    other_job = uuid.uuid4()
    assert (
        client.get(f"/api/v1/jobs/{other_job}/events?ticket={quote(ticket)}").status_code
        == 401
    )


def test_stream_ticket_payload_is_bound_to_user_and_job():
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    ticket, _, _ = issue_stream_ticket(user_id, job_id)

    payload = verify_stream_ticket(ticket, user_id=user_id, job_id=job_id)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["jid"] == str(job_id)
    assert verify_stream_ticket(ticket, user_id=uuid.uuid4(), job_id=job_id) is None
    assert verify_stream_ticket(ticket, user_id=user_id, job_id=uuid.uuid4()) is None
