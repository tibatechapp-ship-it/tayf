"""Atomic job-state races: start, cancel, fail, complete."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import make_session_factory
from app.models import CreditLedger, GenerationJob, GenerationStatus
from app.repositories import project_repository, user_repository
from app.services import credits, job_state


def _seed_job(session, user, *, status: GenerationStatus, charged: int) -> GenerationJob:
    project = project_repository.create_project(
        session, owner_id=user.id, name="race project"
    )
    credits.grant(
        session,
        user.id,
        100,
        "test_funding",
        operation_key=f"funding:{project.id}",
    )
    job = GenerationJob(
        project_id=project.id,
        prompt="race",
        num_scenes=1,
        status=status,
        credits_charged=charged,
        provider_name="mock",
        model_version="mock-1.0",
        input_params={},
    )
    session.add(job)
    session.flush()
    if charged > 0:
        credits.charge(
            session,
            user.id,
            charged,
            "job_charge",
            job_id=job.id,
            operation_key=f"job_charge:{job.id}",
        )
    session.commit()
    return job


def _setup(engine, *, status: GenerationStatus, charged: int):
    factory = make_session_factory(engine)
    with factory() as db:
        owner = user_repository.create_user(
            db,
            email="jobs@example.com",
            username="jobs",
            hashed_password=hash_password("Sup3rSecret!"),
        )
        db.commit()
        job = _seed_job(db, owner, status=status, charged=charged)
        return factory, owner.id, job.id


def test_start_has_single_winner(engine) -> None:
    factory, _, job_id = _setup(engine, status=GenerationStatus.PENDING, charged=0)
    barrier = Barrier(2)

    def claim(_: int) -> bool:
        with factory() as db:
            barrier.wait()
            claimed = job_state.start(db, job_id)
            db.commit()
            return claimed is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))

    assert sum(results) == 1
    with factory() as db:
        assert db.get(GenerationJob, job_id).status == GenerationStatus.PROCESSING


def test_cancel_and_complete_only_one_wins(engine) -> None:
    factory, owner_id, job_id = _setup(
        engine, status=GenerationStatus.PROCESSING, charged=5
    )
    barrier = Barrier(2)

    def cancel(_: int) -> str:
        with factory() as db:
            barrier.wait()
            _, outcome = job_state.cancel(db, job_id, owner_id)
            db.commit()
            return outcome

    def complete(_: int) -> bool:
        with factory() as db:
            barrier.wait()
            done = job_state.complete(
                db,
                job_id,
                result_url="/api/v1/files/jobs/x/video.mp4",
                thumbnail_url=None,
                video_size_bytes=1000,
                duration_seconds=2.0,
                storyboard={"title": "race", "scenes": []},
            )
            db.commit()
            return done

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel, 0)
        complete_future = pool.submit(complete, 0)
        outcomes = (cancel_future.result(), complete_future.result())

    assert outcomes in (("ok", False), ("conflict", True))

    with factory() as db:
        job = db.get(GenerationJob, job_id)
        entries = db.scalars(
            select(CreditLedger).where(CreditLedger.job_id == job_id)
        ).all()
        refunds = [entry for entry in entries if entry.reason.startswith("refund_job")]
        assert len(refunds) <= 1
        if job.status == GenerationStatus.CANCELLED:
            assert len(refunds) == 1
            assert refunds[0].reason == "refund_job_cancelled"
            assert credits.balance_of(db, owner_id) == 100
        else:
            assert job.status == GenerationStatus.COMPLETED
            assert refunds == []
            assert credits.balance_of(db, owner_id) == 95


def test_fail_and_cancel_produce_exactly_one_refund(engine) -> None:
    factory, owner_id, job_id = _setup(
        engine, status=GenerationStatus.PROCESSING, charged=5
    )
    barrier = Barrier(2)

    def fail(_: int) -> bool:
        with factory() as db:
            barrier.wait()
            _, changed = job_state.fail(db, job_id, "provider exploded")
            db.commit()
            return changed

    def cancel(_: int) -> str:
        with factory() as db:
            barrier.wait()
            _, outcome = job_state.cancel(db, job_id, owner_id)
            db.commit()
            return outcome

    with ThreadPoolExecutor(max_workers=2) as pool:
        fail_future = pool.submit(fail, 0)
        cancel_future = pool.submit(cancel, 0)
        fail_future.result()
        cancel_future.result()

    with factory() as db:
        job = db.get(GenerationJob, job_id)
        entries = db.scalars(
            select(CreditLedger).where(CreditLedger.job_id == job_id)
        ).all()
        refunds = [entry for entry in entries if entry.reason.startswith("refund_job")]
        assert len(refunds) == 1
        assert job.credits_charged == 0
        assert credits.balance_of(db, owner_id) == 100
        if job.status == GenerationStatus.FAILED:
            assert refunds[0].reason == "refund_job_failed"
        else:
            assert job.status == GenerationStatus.CANCELLED
            assert refunds[0].reason == "refund_job_cancelled"
