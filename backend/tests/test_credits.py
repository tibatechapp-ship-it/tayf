"""Credits ledger tests (append-only accounting) + job charge integration."""

import time


def test_ledger_has_signup_bonus_entry(client, auth_headers):
    headers, _ = auth_headers
    response = client.get("/api/v1/credits/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["balance"] == 100
    assert body["entries"][0]["reason"] == "signup_bonus"
    assert body["entries"][0]["delta"] == 100
    assert body["entries"][0]["balance_after"] == 100


def test_credits_require_auth(client):
    assert client.get("/api/v1/credits/me").status_code == 401


def _wait_terminal(client, headers, job_id, timeout_s=120) -> dict:
    deadline = time.time() + timeout_s
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("completed", "failed", "rejected"):
            return job
        time.sleep(1.0)
    return job


def test_job_charges_credits(client, auth_headers, project_id):
    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "a calm river at dawn", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202, created.text
    job = _wait_terminal(client, headers, created.json()["id"])
    assert job["status"] == "completed", job

    credits_view = client.get("/api/v1/credits/me", headers=headers).json()
    assert credits_view["balance"] == 98  # 100 - 2 scenes * 1 credit
    reasons = [entry["reason"] for entry in credits_view["entries"]]
    assert reasons[:2] == ["job_charge", "signup_bonus"]
    charge_entry = credits_view["entries"][0]
    assert charge_entry["delta"] == -2
    assert charge_entry["balance_after"] == 98
    assert charge_entry["job_id"] == job["id"]


def test_insufficient_credits_returns_402(client, auth_headers, project_id):
    headers, _ = auth_headers
    # burn the balance on max-size jobs (8 scenes each: 100 -> 92 -> 84 ...)
    while True:
        response = client.post(
            f"/api/v1/projects/{project_id}/jobs",
            json={"prompt": "burn it down", "num_scenes": 8},
            headers=headers,
        )
        if response.status_code == 402:
            break
        assert response.status_code == 202, response.text
        _wait_terminal(client, headers, response.json()["id"])

    body = response.json()
    assert "رصيدك غير كافٍ" in body["detail"]
    # and the failed attempt charged nothing
    balance = client.get("/api/v1/credits/me", headers=headers).json()
    assert balance["balance"] < 8
