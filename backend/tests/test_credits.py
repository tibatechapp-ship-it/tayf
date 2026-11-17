"""Credits ledger tests (append-only accounting) + job charge integration."""

import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import make_session_factory
from app.models import CreditLedger
from app.repositories import user_repository
from app.services import credits


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


def test_concurrent_charges_do_not_overdraw(engine) -> None:
    factory = make_session_factory(engine)
    with factory() as setup:
        owner = user_repository.create_user(
            setup,
            email="race@example.com",
            username="race",
            hashed_password=hash_password("Sup3rSecret!"),
        )
        credits.grant(setup, owner.id, 100, "test_funding", operation_key="race:funding")
        setup.commit()
        user_id = owner.id

    def attempt(index: int) -> str:
        with factory() as db:
            try:
                credits.charge(
                    db,
                    user_id,
                    60,
                    "race_charge",
                    operation_key=f"race:charge:{index}",
                )
                db.commit()
                return "charged"
            except credits.InsufficientCredits:
                db.rollback()
                return "insufficient"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))

    assert results.count("charged") == 1
    assert results.count("insufficient") == 3

    with factory() as db:
        assert credits.balance_of(db, user_id) == 40
        entries = db.scalars(
            select(CreditLedger).where(CreditLedger.user_id == user_id)
        ).all()
        charges = [entry for entry in entries if entry.reason == "race_charge"]
        assert len(charges) == 1
        assert charges[0].delta == -60
        assert charges[0].balance_after == 40


def test_duplicate_operation_key_is_noop(session, user) -> None:
    first = credits.grant(session, user.id, 10, "bonus", operation_key="grant:repeat")
    session.commit()

    second = credits.grant(session, user.id, 10, "bonus", operation_key="grant:repeat")
    session.commit()

    assert second.id == first.id
    assert credits.balance_of(session, user.id) == 10
    entries = session.scalars(
        select(CreditLedger).where(CreditLedger.operation_key == "grant:repeat")
    ).all()
    assert len(entries) == 1


def test_duplicate_charge_key_does_not_charge_twice(session, user) -> None:
    credits.grant(session, user.id, 100, "test_funding", operation_key="funding:once")
    first = credits.charge(session, user.id, 30, "job_charge", operation_key="charge:same")
    session.commit()

    second = credits.charge(session, user.id, 30, "job_charge", operation_key="charge:same")
    session.commit()

    assert second.id == first.id
    assert credits.balance_of(session, user.id) == 70
    entries = session.scalars(
        select(CreditLedger).where(CreditLedger.operation_key == "charge:same")
    ).all()
    assert len(entries) == 1
