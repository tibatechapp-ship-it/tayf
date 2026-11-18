"""Human approval gates: opt-in per job, resumable, auditable, refundable."""

from __future__ import annotations

import time

TERMINAL = {"completed", "failed", "rejected", "cancelled"}


def _create_job(client, headers, project_id: str, *, approve: bool = True) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "فيديو بمراجعة بشرية", "num_scenes": 2, "require_approvals": approve},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def _get(client, headers, job_id: str) -> dict:
    return client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()


def _wait_gate(client, headers, job_id: str, stage: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _get(client, headers, job_id)
        gate = job.get("pending_approval") or {}
        if gate.get("stage") == stage and gate.get("decision") is None:
            return job
        if job["status"] in TERMINAL:
            break
        time.sleep(0.1)
    raise AssertionError(f"gate {stage!r} never opened: {_get(client, headers, job_id)}")


def _wait_status(client, headers, job_id: str, wanted: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _get(client, headers, job_id)
        if job["status"] == wanted:
            return job
        time.sleep(0.1)
    raise AssertionError(f"status {wanted!r} not reached: {_get(client, headers, job_id)}")


def _decide(client, headers, job_id: str, decision: str, note: str = ""):
    return client.post(
        f"/api/v1/jobs/{job_id}/approval",
        json={"decision": decision, "note": note},
        headers=headers,
    )


def test_approval_gates_pause_and_resume_without_regeneration(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id)
    job_id = created["id"]

    script_gate = _wait_gate(client, headers, job_id, "storyboard")
    assert script_gate["status"] == "processing"
    assert script_gate["require_approvals"] is True
    assert script_gate["output_url"] is None
    assert script_gate["scenes"][0]["description"]
    assert script_gate["scenes"][0]["image_prompt"]
    assert script_gate["approval_history"] == []

    approved = _decide(client, headers, job_id, "approve", "النص جيد")
    assert approved.status_code == 200, approved.text

    asset_gate = _wait_gate(client, headers, job_id, "assets")
    assert asset_gate["output_url"] is None
    assert asset_gate["scenes"][0]["image_url"]
    assert len(asset_gate["approval_history"]) == 1
    assert asset_gate["approval_history"][0]["note"] == "النص جيد"

    assert _decide(client, headers, job_id, "approve").status_code == 200
    done = _wait_status(client, headers, job_id, "completed")
    assert done["output_url"]
    assert [item["decision"] for item in done["approval_history"]] == ["approve", "approve"]
    assert done["pending_approval"] is None  # consumed after resume

    proof = client.get(f"/api/v1/jobs/{job_id}/proof", headers=headers).json()
    stages = [event["stage"] for event in proof["events"]]
    assert stages.count("keyframes") == 1  # resume reused stored frames
    assert "approval:storyboard" in stages
    assert "approval:assets" in stages


def test_rejecting_a_gate_cancels_and_refunds(client, auth_headers, project_id):
    import uuid

    from app.db.session import SessionLocal
    from app.models import CreditLedger, User

    headers, login = auth_headers
    username = login["user"]["username"]
    created = _create_job(client, headers, project_id)
    job_id = created["id"]
    _wait_gate(client, headers, job_id, "storyboard")

    response = _decide(client, headers, job_id, "reject", "أعد الكتابة")
    assert response.status_code == 200, response.text
    cancelled = _wait_status(client, headers, job_id, "cancelled")
    assert cancelled["approval_history"][0]["decision"] == "reject"
    assert cancelled["approval_history"][0]["note"] == "أعد الكتابة"

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        entries = (
            db.query(CreditLedger)
            .filter(CreditLedger.user_id == user.id, CreditLedger.job_id == uuid.UUID(job_id))
            .all()
        )
        assert sum(entry.delta for entry in entries) == 0  # charge + refund


def test_approval_requires_owner_and_single_decision(client, auth_headers, project_id):
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    job_id = _create_job(client, headers, project_id)["id"]
    _wait_gate(client, headers, job_id, "storyboard")
    url = f"/api/v1/jobs/{job_id}/approval"

    assert client.post(url, json={"decision": "approve"}).status_code == 401
    other = register_and_login(client, username="gate_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.post(url, json={"decision": "approve"}, headers=other_headers).status_code == 404

    assert _decide(client, headers, job_id, "reject").status_code == 200
    # A rejected gate is terminal: no second decision can be accepted.
    assert _decide(client, headers, job_id, "approve").status_code == 409


def test_automated_jobs_have_no_gate(client, auth_headers, project_id):
    headers, _ = auth_headers
    job_id = _create_job(client, headers, project_id, approve=False)["id"]
    done = _wait_status(client, headers, job_id, "completed")
    assert done["require_approvals"] is False
    assert done["approval_history"] == []
