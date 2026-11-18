"""Verifiable per-stage proof: hash chain, signature and owner-scoped API."""

from __future__ import annotations

import copy
import time
import uuid
from datetime import datetime, timezone

from app.core import job_proof

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


def test_chain_detects_tampered_fields_and_broken_links():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = job_proof.make_event(
        seq=1,
        stage="storyboard",
        started_at=started,
        finished_at=started,
        inputs={"prompt": "original"},
    )
    second = job_proof.make_event(
        seq=2,
        stage="store",
        started_at=started,
        finished_at=started,
        prev_hash=first["event_hash"],
    )
    assert job_proof.verify_events([first, second])["valid"] is True

    edited = copy.deepcopy([first, second])
    edited[0]["inputs"]["prompt"] = "changed"
    broken = job_proof.verify_events(edited)
    assert broken["valid"] is False
    assert broken["broken_at"] == 1

    relinked = copy.deepcopy([first, second])
    relinked[1]["prev_hash"] = "f" * 64
    assert job_proof.verify_events(relinked)["valid"] is False


def test_signature_and_public_hash_detect_edits():
    document = {"job_id": str(uuid.uuid4()), "events": [], "proof_version": 1}
    signature = job_proof.sign_document(document)
    assert job_proof.verify_document(document, signature) is True

    edited = {**document, "job_id": str(uuid.uuid4())}
    assert job_proof.verify_document(edited, signature) is False
    assert job_proof.document_hash(edited) != job_proof.document_hash(document)


def test_completed_job_exposes_verifiable_proof(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "مشهد مع إثبات قابل للتحقق")
    job = _wait_terminal(client, headers, created["id"])
    assert job["status"] == "completed", job

    response = client.get(f"/api/v1/jobs/{job['id']}/proof", headers=headers)
    assert response.status_code == 200, response.text
    proof = response.json()

    assert proof["job_id"] == job["id"]
    assert proof["chain"]["valid"] is True
    assert proof["chain"]["count"] == len(proof["events"])
    stages = [event["stage"] for event in proof["events"]]
    assert "storyboard" in stages
    assert "safety_text" in stages
    assert "store" in stages
    assert all(event["verification"]["allowed"] for event in proof["events"])
    assert proof["document"]["model_version"] == "mock-1.0"
    assert proof["document"]["credits_charged"] == 2
    assert job_proof.document_hash(proof["document"]) == proof["document_hash"]
    assert job_proof.verify_document(proof["document"], proof["signature"]) is True


def test_proof_requires_auth_and_is_owner_scoped(client, auth_headers, project_id):
    from tests.conftest import register_and_login

    headers, _ = auth_headers
    created = _create_job(client, headers, project_id, "إثبات خاص")
    job = _wait_terminal(client, headers, created["id"])
    url = f"/api/v1/jobs/{job['id']}/proof"

    assert client.get(url).status_code == 401
    other = register_and_login(client, username="proof_snooper")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(url, headers=other_headers).status_code == 404
    assert client.get(url, headers=headers).status_code == 200
