# Architecture — Tayf Studio

Status: **current as of 2026-11-18**. This document describes shipped
behavior, verified by CI run `44281037955` (197 passed, 82.57% coverage).

## 1. Component map

```
Browser (React 19 + TS, RTL-first)
  │  same-origin /api
  ▼
Vite dev server / nginx
  │
  ▼
FastAPI application
  ├── api/            HTTP concerns, auth, rate limits, SSE tickets
  ├── services/       business rules, provider calls, credits, moderation
  ├── repositories/   the only layer issuing ORM queries
  └── models/schemas  DB tables vs wire contracts
        │
        ├── SQLite (dev/Termux) or PostgreSQL (prod)
        ├── local filesystem or S3-compatible storage
        ├── AI providers: mock | zai_gateway | openai_compatible | replicate_t2v
        ├── Stripe Checkout + signed webhook
        └── external moderation HTTP service (optional)
```

A durable worker (`python -m app.worker`) claims leased jobs in production
compose. In development/tests, Starlette `BackgroundTasks` runs the same
pipeline in-process, which keeps the suite deterministic.

## 2. Layer boundaries

| Layer | Location | Rule |
| --- | --- | --- |
| HTTP | `backend/app/api/` | validation, status codes, auth; no SQL, no business rules |
| Business | `backend/app/services/` | pricing, lifecycle, refunds, provider calls, payments |
| Persistence | `backend/app/repositories/` | only place with queries/ORM; ownership enforced here |
| Models/schemas | `backend/app/models/`, `backend/app/schemas/` | tables vs wire contracts, kept separate |
| Providers | `backend/app/services/ai/` | one adapter per vendor behind one interface |
| Storage | `backend/app/services/storage/` | neutral keys, `store/get/exists/delete/iter`, fresh signed URLs, TTL cleanup |
| Frontend | `frontend/src/{views,services,i18n,styles}` | no business rules, zero mock data |

## 3. Generation lifecycle

1. `POST /projects/{id}/jobs` → JWT authentication → project ownership check.
2. Local safety screen (length, blocklist, optional external moderator).
   Rejection writes a `rejected` job row and charges nothing.
3. One transaction: insert `PENDING` job → `flush()` to obtain its id →
   ledger `job_charge` entry carrying that id → commit.
4. `202 Accepted` with the job contract. The pipeline then runs in the worker
   or as a background task.
5. Pipeline checkpoints persist `progress` and `stage` at 10/30/40/70/85:
   storyboard → AI-text safety screen → keyframes or native T2V → thumbnail →
   artifact storage → `completed`.
6. SSE endpoint streams `progress`/`done` events using a 5-minute HMAC ticket;
   the frontend falls back to 4-second polling.
7. Any failure emits a full refund ledger entry with a unique operation key.

## 4. Concurrency and recovery

- `generation_jobs` is the queue: `worker_id`, `lease_until`, `attempts`.
- Workers renew leases at `JOB_LEASE_SECONDS/3`.
- Expired leases are reclaimed by another worker; the API can restart without
  losing work when `EXTERNAL_JOB_WORKER=true`.
- SQLite uses WAL and `PRAGMA foreign_keys=ON`.
- CPU-bound ffmpeg work runs in a thread; provider I/O uses `httpx`.

## 5. Credit and payment integrity

- `credit_ledger` is append-only; balance is the sum of deltas.
- Every movement has an `operation_key` unique constraint.
- Job charges use `job_charge:<job_id>`.
- Stripe top-ups use `stripe:<sha256(session_id)>`.
- Credits are granted only after a paid webhook whose amount, currency and
  package match the server-owned package definition.

## 6. Safety and moderation

- Local blocklist runs first, so known-bad prompts never leave the process.
- When `MODERATION_API_URL` is set, the external moderator sees normalized
  prompt text and AI-produced storyboard text.
- Transport errors, timeouts, non-2xx responses and malformed verdicts reject
  with `moderation_unavailable` unless `MODERATION_FAIL_CLOSED=false`.

## 7. Honesty and observability

- `mock` provider output is stamped `SIMULATED` and `simulated=true`.
- `replicate_t2v` stores the vendor MP4/WebM directly; no keyframes are faked.
- `/metrics` exposes aggregate counters only.
- Every response carries security headers and an `X-Request-ID`.

## 8. Known limits

- The in-process rate limiter is per replica; use an edge limiter for multi-replica deployments.
- SQLite remains a portable default, not a high-concurrency production database.
- Replicate/Payments providers require operator-owned keys and webhook secrets.
- GitHub Actions are not yet SHA-pinned; tracked as release-hardening debt.
