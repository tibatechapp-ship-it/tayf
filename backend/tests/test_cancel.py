"""Job cancellation: refunds, state transitions, and abuse rejection.

Note on determinism: under TestClient the generation pipeline keeps running in
the portal event loop AFTER the 202 returns (like production). These tests
poll the job to a terminal state first, then manipulate/read it — no races.
"""

import time
import uuid

from app.db.session import SessionLocal
from app.models import CreditLedger, GenerationJob, GenerationStatus

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def _create_job(client, headers, project_id: str, prompt: str, num_scenes: int = 2) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": prompt, "num_scenes": num_scenes},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def _wait_terminal(client, headers, job_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline and job["status"] not in TERMINAL:
        time.sleep(0.5)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    return job


def _cancel(client, headers, job_id: str):
    return client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)


def _with_db(fn):
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


def test_pending_job_cancel_refunds(client, project_id, auth_headers):
    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "مشهد ليتم إلغاؤه", num_scenes=3)
    job = _wait_terminal(client, headers, job["id"])
    assert job["status"] == "completed", job  # mock pipeline is reliable

    # Reset the finished row to PENDING: the exact state a slow provider would
    # leave between the create call and the pipeline's first commit.
    job_uuid = uuid.UUID(job["id"])

    def make_pending(db):
        fresh = db.get(GenerationJob, job_uuid)
        fresh.status = GenerationStatus.PENDING
        fresh.completed_at = None
        fresh.credits_charged = 3
        db.commit()

    _with_db(make_pending)

    response = _cancel(client, headers, job["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["credits_charged"] == 0

    def refund_entries(db):
        return [
            (e.reason, e.delta)
            for e in db.query(CreditLedger).filter(CreditLedger.job_id == job_uuid).all()
        ]

    reasons = dict(_with_db(refund_entries))
    assert reasons.get("refund_job_cancelled") == 3
    assert reasons.get("job_charge") == -3


def test_terminal_job_cannot_be_cancelled(client, project_id, auth_headers):
    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "مهمة مكتملة")
    job = _wait_terminal(client, headers, job["id"])
    assert job["status"] == "completed", job
    assert _cancel(client, headers, job["id"]).status_code == 409


def test_cancel_other_users_job_is_404(client, project_id, auth_headers):
    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "مهمة الغريب")
    stranger = client.post(
        "/api/v1/auth/register",
        json={
            "email": "stranger@example.com",
            "username": "stranger",
            "password": "Sup3rSecret!",
        },
    ).json()
    assert _cancel(client, {"Authorization": f"Bearer {stranger['access_token']}"}, job["id"]).status_code == 404


def test_cancel_requires_auth(client, project_id, auth_headers):
    headers, _ = auth_headers
    job = _create_job(client, headers, project_id, "بدون توكن")
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 401


def test_cancel_unknown_job_is_404(client, auth_headers):
    headers, _ = auth_headers
    assert _cancel(client, headers, str(uuid.uuid4())).status_code == 404
