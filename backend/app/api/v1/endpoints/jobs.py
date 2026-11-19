"""Jobs endpoints: create (safety -> credits -> background pipeline) and read.

Job execution has two modes: by default the pipeline runs as a Starlette
background task AFTER the 202 response (deterministic under TestClient);
with EXTERNAL_JOB_WORKER=true the job stays PENDING for the durable worker
to claim, so an API restart cannot lose it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core import job_proof
from app.core.branding import branding_snapshot
from app.core.config import get_settings
from app.core.metrics import record_job_terminal
from app.core.ratelimit import job_rate_limit
from app.core.safety import get_safety_layer
from app.core.stream_tickets import issue_stream_ticket, verify_stream_ticket
from app.db.session import get_session
from app.models import GenerationJob, GenerationStatus, Project, User
from app.repositories import job_repository
from app.schemas.job import (
    ApprovalDecisionIn,
    JobCreateIn,
    JobOut,
    JobProofOut,
    JobProgressEvent,
    ProofChainOut,
    ProofEventOut,
    StreamTicketOut,
)
from app.services import approvals, credits, job_state
from app.services.pipeline import run_job_pipeline

router = APIRouter(tags=["jobs"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

STREAM_TICKET_TTL_SECONDS = 300
STREAM_MAX_SECONDS = 900
STREAM_POLL_SECONDS = 1.0
STREAM_HEARTBEAT_SECONDS = 15.0
TERMINAL_STATUSES = frozenset(item.value for item in GenerationStatus.terminal())


def _get_owned_project(session: Session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.user_id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المشروع غير موجود")
    return project


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a generation job (safety -> credits -> pipeline)",
    responses={
        402: {"description": "Insufficient credits"},
        404: {"description": "Project not found or not owned by this user"},
    },
)
def create_job(
    project_id: uuid.UUID,
    payload: JobCreateIn,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    session: SessionDep,
    _rl: None = Depends(job_rate_limit),
) -> JobOut:
    settings = get_settings()
    project = _get_owned_project(session, project_id, current_user.id)
    branding = branding_snapshot(current_user.plan)
    safety = get_safety_layer()
    cost = payload.num_scenes * get_settings().CREDIT_PER_SCENE

    # 1) pre-generation safety screen (no charge on rejection)
    verdict = safety.check_prompt(payload.prompt)
    if not verdict.allowed:
        job = GenerationJob(
            project_id=project.id,
            prompt=payload.prompt,
            num_scenes=payload.num_scenes,
            aspect=payload.aspect,
            style=payload.style,
            input_params={"branding": branding},
            provider_name="safety",
            model_version="pre-filter",
            status=GenerationStatus.REJECTED,
            progress=100,
            stage="rejected",
            rejection_reason=verdict.reason,
            safety_category=verdict.category,
            credits_charged=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        record_job_terminal(GenerationStatus.REJECTED.value)
        return JobOut.from_model(job)

    # 2) create the job row FIRST (uncommitted) so the charge entry can carry
    #    its id — the ledger must be auditable down to the exact job.
    job = GenerationJob(
        project_id=project.id,
        prompt=payload.prompt,
        num_scenes=payload.num_scenes,
        aspect=payload.aspect,
        style=payload.style,
        input_params={"requested_by": str(current_user.id), "branding": branding},
        status=GenerationStatus.PENDING,
        credits_charged=cost,
        require_approvals=payload.require_approvals,
    )
    session.add(job)
    session.flush()  # assigns job.id without committing

    cost = job.credits_charged
    try:
        credits.charge(
            session,
            current_user.id,
            cost,
            reason="job_charge",
            job_id=job.id,
            operation_key=f"job_charge:{job.id}",
        )
    except credits.InsufficientCredits as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"رصيدك غير كافٍ: تحتاج {exc.needed} رصيدًا ولديك {exc.available}. "
                f"كل مشهد يكلف {settings.CREDIT_PER_SCENE} رصيدًا."
            ),
        ) from exc

    session.commit()
    session.refresh(job)

    if not settings.EXTERNAL_JOB_WORKER:
        # Dev/test single-process path. In production the external worker
        # claims the PENDING row, so the pipeline survives an API restart.
        background_tasks.add_task(run_job_pipeline, str(job.id))
    return JobOut.from_model(job)


@router.get(
    "/projects/{project_id}/jobs",
    response_model=list[JobOut],
    summary="List a project's jobs (newest first)",
)
def list_jobs(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobOut]:
    project = _get_owned_project(session, project_id, current_user.id)
    jobs = job_repository.list_jobs_by_project(
        session, project.id, limit=limit, offset=offset
    )
    return [JobOut.from_model(job) for job in jobs]


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobOut,
    summary="Cancel a pending/processing job (credits are refunded)",
    responses={
        404: {"description": "Job not found or not owned by this user"},
        409: {"description": "Job already reached a terminal state"},
    },
)
def cancel_job(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> JobOut:
    job, outcome = job_state.cancel(session, job_id, current_user.id)
    if outcome == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    if outcome == "conflict":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="لا يمكن إلغاء مهمة منتهية"
        )
    session.commit()
    session.refresh(job)
    record_job_terminal(GenerationStatus.CANCELLED.value)
    return JobOut.from_model(job)


@router.post(
    "/jobs/{job_id}/approval",
    response_model=JobOut,
    summary="Approve or reject the open stage gate (reject refunds credits)",
    responses={
        404: {"description": "Job not found or not owned by this user"},
        409: {"description": "No open approval gate on this job"},
    },
)
def decide_approval(
    job_id: uuid.UUID,
    payload: ApprovalDecisionIn,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    session: SessionDep,
) -> JobOut:
    outcome, gate = approvals.decide_gate(
        session, job_id, current_user.id, payload.decision, payload.note
    )
    if outcome == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    if outcome == "conflict":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="لا توجد موافقة معلقة لهذه المهمة"
        )
    if payload.decision == "reject":
        _job, outcome = job_state.cancel(session, job_id, current_user.id)
        if outcome != "ok":  # pragma: no cover - the gate UPDATE already guarded this
            raise HTTPException(status.HTTP_409_CONFLICT, detail="تعذر إلغاء المهمة")
        session.commit()
        record_job_terminal(GenerationStatus.CANCELLED.value)
    else:
        assert gate is not None  # guaranteed by decide_gate's "ok" outcome
        background_tasks.add_task(run_job_pipeline, str(job_id), resume_from=gate["stage"])
    session.expire_all()
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    return JobOut.from_model(job)


@router.get(
    "/jobs/{job_id}",
    response_model=JobOut,
    summary="Read one job (poll for progress)",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def get_job(job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep) -> JobOut:
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    return JobOut.from_model(job)


@router.get(
    "/jobs/{job_id}/proof",
    response_model=JobProofOut,
    summary="Verifiable per-stage proof (inputs, model, timings, cost, verdicts)",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def get_job_proof(
    job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> JobProofOut:
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    document = job_proof.build_document(job)
    events = document["events"]
    return JobProofOut(
        job_id=job.id,
        proof_version=job_proof.PROOF_VERSION,
        document=document,
        events=[ProofEventOut.model_validate(event) for event in events],
        document_hash=job_proof.document_hash(document),
        signature=job_proof.sign_document(document),
        chain=ProofChainOut.model_validate(job_proof.verify_events(events)),
    )


def _stream_snapshot(
    session: Session, job_id: uuid.UUID, owner_id: uuid.UUID
) -> JobProgressEvent | None:
    """Fresh progress snapshot, read off-thread so SSE does not block the loop."""
    session.expire_all()
    job = job_repository.get_job_owned_by(session, job_id, owner_id)
    return None if job is None else JobProgressEvent.from_model(job)


@router.post(
    "/jobs/{job_id}/stream-ticket",
    response_model=StreamTicketOut,
    summary="Mint a short-lived ticket for the job SSE stream",
    responses={404: {"description": "Job not found or not owned by this user"}},
)
def create_stream_ticket(
    job_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> StreamTicketOut:
    job = job_repository.get_job_owned_by(session, job_id, current_user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")
    ticket, expires_at, expires_in = issue_stream_ticket(
        current_user.id, job.id, ttl_seconds=STREAM_TICKET_TTL_SECONDS
    )
    return StreamTicketOut(
        job_id=job.id, ticket=ticket, expires_at=expires_at, expires_in=expires_in
    )


@router.get(
    "/jobs/{job_id}/events",
    summary="Server-Sent Events stream for one job's live progress",
    responses={
        401: {"description": "Missing, invalid, expired or mismatched stream ticket"},
        404: {"description": "Job not found or not owned by the ticket's user"},
    },
)
async def stream_job_events(
    job_id: uuid.UUID,
    ticket: Annotated[str, Query(min_length=1)],
    session: SessionDep,
) -> StreamingResponse:
    claims = verify_stream_ticket(ticket, job_id=job_id)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="تذكرة البث غير صالحة")
    try:
        owner_id = uuid.UUID(str(claims.get("sub", "")))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="تذكرة البث غير صالحة") from exc
    if await run_in_threadpool(job_repository.get_job_owned_by, session, job_id, owner_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة")

    async def event_stream():
        loop = asyncio.get_running_loop()
        started = loop.time()
        last_heartbeat = started
        last_signature: tuple | None = None
        yield ": connected\n\n"
        while loop.time() - started < STREAM_MAX_SECONDS:
            snapshot = await run_in_threadpool(_stream_snapshot, session, job_id, owner_id)
            if snapshot is None:
                yield "event: error\ndata: {\"detail\":\"job disappeared\"}\n\n"
                return
            signature = (
                snapshot.status.value,
                snapshot.progress,
                snapshot.stage,
                snapshot.error_message,
                snapshot.rejection_reason,
                snapshot.completed_at,
            )
            if signature != last_signature:
                last_signature = signature
                yield f"event: progress\ndata: {snapshot.model_dump_json()}\n\n"
                if snapshot.status.value in TERMINAL_STATUSES:
                    yield "event: done\ndata: {}\n\n"
                    return
            now = loop.time()
            if now - last_heartbeat >= STREAM_HEARTBEAT_SECONDS:
                yield ": keep-alive\n\n"
                last_heartbeat = now
            await asyncio.sleep(STREAM_POLL_SECONDS)
        yield "event: error\ndata: {\"detail\":\"stream timeout\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
