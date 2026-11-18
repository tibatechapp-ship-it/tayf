"""Durable job worker — claims queued jobs and runs the pipeline.

Run as its own process (`python -m app.worker`). Jobs live in the
`generation_jobs` table with a time-limited lease, so an API restart or a
killed worker cannot lose a job: startup recovery requeues expired leases and
another worker picks them up.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import uuid

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import job_queue
from app.services.pipeline import run_job_pipeline


def _worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"[:64]


async def _heartbeat(
    job_id: uuid.UUID,
    worker_id: str,
    stop: asyncio.Event,
    lost: asyncio.Event,
    lease_seconds: int,
) -> None:
    interval = max(lease_seconds / 3, 1)
    while not stop.is_set():
        try:
            await asyncio.sleep(interval)
            if stop.is_set():
                return
            with SessionLocal() as db:
                if not job_queue.renew_lease(db, job_id, worker_id, lease_seconds=lease_seconds):
                    lost.set()  # ownership gone — the pipeline stops at its next checkpoint
                    return
        except asyncio.CancelledError:
            return
        except Exception as exc:  # transient DB error; lease expiry is the backstop
            print(f"[worker] heartbeat error for {job_id}: {exc}")


async def run_worker() -> None:
    settings = get_settings()
    worker_id = _worker_id()
    lease_seconds = max(settings.JOB_LEASE_SECONDS, 30)
    poll_seconds = max(settings.JOB_POLL_SECONDS, 0.1)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)

    with SessionLocal() as db:
        recovered = job_queue.recover_stale(db)
    if recovered:
        print(f"[worker] recovered {recovered} orphaned job(s)")

    print(f"[worker] {worker_id} ready (lease={lease_seconds}s, poll={poll_seconds}s)")
    try:
        while not stop.is_set():
            with SessionLocal() as db:
                try:
                    job = job_queue.claim_next(db, worker_id, lease_seconds=lease_seconds)
                except Exception as exc:
                    print(f"[worker] claim error: {exc}")
                    job = None
            if job is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
                continue

            lost = asyncio.Event()
            heartbeat = asyncio.create_task(
                _heartbeat(job.id, worker_id, stop, lost, lease_seconds)
            )
            try:
                await run_job_pipeline(job.id, claimed_by=worker_id, should_stop=lost.is_set)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
    finally:
        with SessionLocal() as db:
            released = job_queue.release_owned(db, worker_id)
        if released:
            print(f"[worker] released {released} job(s) on shutdown")
        print(f"[worker] {worker_id} stopped")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
