"""Durable queue: claim ownership, lease recovery and graceful release."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from app.db.session import make_session_factory
from app.models import GenerationJob, GenerationStatus
from app.services import job_queue


def _seed_job(session, user, *, status=GenerationStatus.PENDING) -> GenerationJob:
    from app.repositories import project_repository

    project = project_repository.create_project(session, owner_id=user.id, name="queue project")
    job = GenerationJob(
        project_id=project.id,
        prompt="queue",
        num_scenes=1,
        status=status,
        credits_charged=0,
        provider_name="mock",
        model_version="mock-1.0",
        input_params={},
    )
    session.add(job)
    session.commit()
    return job


def test_claim_next_has_single_winner(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        job = _seed_job(db, user)
        job_id = job.id
    barrier = Barrier(2)

    def claim(_: int) -> bool:
        with factory() as db:
            barrier.wait()
            return job_queue.claim_next(db, f"worker-{_}") is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))

    assert sum(results) == 1
    with factory() as db:
        stored = db.get(GenerationJob, job_id)
        assert stored.status == GenerationStatus.PROCESSING
        assert stored.worker_id is not None
        assert stored.attempts == 1


def test_recover_stale_requeues_expired_lease(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        job_id = _seed_job(db, user).id
    with factory() as db:
        assert job_queue.claim_next(db, "dead-worker", lease_seconds=-1) is not None
    with factory() as db:
        assert job_queue.recover_stale(db) == 1
    with factory() as db:
        stored = db.get(GenerationJob, job_id)
        assert stored.status == GenerationStatus.PENDING
        assert stored.worker_id is None
        assert stored.lease_until is None


def test_recover_stale_keeps_live_lease(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        _seed_job(db, user)
    with factory() as db:
        assert job_queue.claim_next(db, "live-worker", lease_seconds=600) is not None
    with factory() as db:
        assert job_queue.recover_stale(db) == 0
    with factory() as db:
        stored = db.scalar(select(GenerationJob).where(GenerationJob.worker_id == "live-worker"))
        assert stored.status == GenerationStatus.PROCESSING


def test_renew_lease_is_owner_guard(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        job_id = _seed_job(db, user).id
    with factory() as db:
        assert job_queue.claim_next(db, "owner") is not None
    with factory() as db:
        assert job_queue.renew_lease(db, job_id, "intruder") is False
        assert job_queue.renew_lease(db, job_id, "owner") is True


def test_release_owned_requeues(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        job_id = _seed_job(db, user).id
    with factory() as db:
        job_queue.claim_next(db, "owner")
    with factory() as db:
        assert job_queue.release_owned(db, "owner") == 1
    with factory() as db:
        stored = db.get(GenerationJob, job_id)
        assert stored.status == GenerationStatus.PENDING
        assert stored.worker_id is None


def test_external_worker_mode_leaves_job_pending(client, auth_headers, project_id, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "EXTERNAL_JOB_WORKER", True)
    headers, _ = auth_headers
    response = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "queued", "num_scenes": 2},
        headers=headers,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"


def test_reclaim_increments_attempts(engine, user) -> None:
    factory = make_session_factory(engine)
    with factory() as db:
        _seed_job(db, user)
    with factory() as db:
        job_queue.claim_next(db, "dead-worker", lease_seconds=-1)
    with factory() as db:
        job_queue.recover_stale(db)
    with factory() as db:
        claimed = job_queue.claim_next(db, "second-worker")
    assert claimed is not None
    assert claimed.attempts == 2
