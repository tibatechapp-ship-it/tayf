# Architecture — VisionForge Studio (target state)

Status: **design document**. Only the `health` slice exists in code today
(Stage 1). Everything else below is planned and is marked as such.

## 1. Component map

```
┌──────────────┐        HTTPS / WSS        ┌───────────────────────────────┐
│  Browser     │ ────────────────────────▶ │  Nginx / reverse proxy (TLS)  │
│  React + TS  │ ◀──────────────────────── │                               │
└──────────────┘                           └───────┬───────────────┬───────┘
                                                   │ /api,/ws      │ /media
                                          ┌────────▼────────┐  ┌───▼─────────┐
                                          │ FastAPI (app)   │  │ S3 / MinIO  │
                                          │ api→service→repo│  │ presigned   │
                                          └───┬────────┬────┘  └─────────────┘
                                              │        │
                             ┌────────────────▼──┐  ┌──▼─────────────────┐
                             │ PostgreSQL        │  │ Redis              │
                             │ (source of truth) │  │ queue + pub/sub    │
                             └───────────────────┘  └──┬─────────────────┘
                                                       │
                                              ┌────────▼─────────┐
                                              │ Worker (Celery)  │
                                              │ provider adapter │
                                              └────────┬─────────┘
                                                       │ HTTPS
                                              ┌────────▼─────────┐
                                              │ AI video provider│
                                              └──────────────────┘
```

## 2. Layer boundaries (enforced by directory layout)

| Layer | Location | Rule |
|---|---|---|
| HTTP | `backend/app/api/` | validation + status codes only, no SQL, no business rules |
| Business | `backend/app/services/` | pricing, job lifecycle, authorization decisions |
| Persistence | `backend/app/repositories/` | the only place with queries/ORM |
| Models/schemas | `models/`, `schemas/` | DB tables vs wire contracts, kept separate |
| Providers | `backend/app/providers/` | one adapter per vendor behind a single interface |
| Workers | `backend/app/workers/` | long tasks, idempotent by job id |
| Frontend | `frontend/src/{pages,features,components,services,stores}` | components never contain business rules |

## 3. Data flow: a generation request (planned, Stage 7–9)

1. `POST /api/v1/generations` → auth → quota/balance check → **one DB
   transaction**: create `generation_jobs` row (`queued`) + ledger *hold* entry.
2. Commit, then enqueue `job_id` (never the whole payload) to Redis.
3. Worker: `validating` → provider submit → store `provider_job_id` →
   `submitted`/`processing`. Every transition is a DB write first, then a
   pub/sub publish.
4. Provider polling/webhook updates the job; on success the artifact is copied
   to object storage and a `videos` row is created; the hold is settled
   (capture or refund) in a single transaction.
5. WebSocket only *notifies* — the client always re-reads
   `GET /api/v1/generations/{id}` on connect, so a missed message is harmless.

## 4. Key decisions and why

| Decision | Why | Alternative rejected |
|---|---|---|
| FastAPI + Pydantic v2 | matches available runtime, typed contracts → OpenAPI for free | Django (heavier, less natural async for provider polling) |
| PostgreSQL + Alembic | real constraints, transactional billing, JSONB for provider payloads | SQLite (no row locks for credit settlement, weak concurrency story) |
| Append-only credit ledger, corrections as reversing entries | auditable money trail; no in-place edits | mutable `balance` column (loses history, invites drift) |
| Celery + Redis, DB as source of truth | survives worker restart, simple on one box | Kafka (operational cost with no proven need) |
| S3-compatible storage + presigned URLs | backend never proxies large files; provider keys stay server-side | serving media from the app process (memory pressure on a phone) |
| WebSocket as notification, REST as truth | reconnection/alerts cannot corrupt state | WebSocket-only state (loses data on drop) |
| Provider capability registry | vendors differ (durations, aspect ratios, audio, cancellation) | one "generate" signature for all vendors (fails silently) |
| Vite dev proxy | one browser origin in dev, no CORS drift | per-environment CORS lists |
| TypeScript 5.9 pinned | TS 7 native compiler has no android-arm64 binary | TS 7 (unusable on this device) |

## 5. Non-goals for the first production milestone

Kubernetes, Kafka, microservices, multi-region, GraphQL. Each adds operational
cost that a solo-operator deployment cannot absorb before load data exists.

## 6. Security invariants

- Provider API keys never reach the browser; the frontend sees only our API.
- Price, credit cost and role are computed server-side from DB state.
- Every resource read/write goes through an ownership check on the server.
- Refresh tokens rotate; reuse invalidates the family.
- Uploads: type + size allow-list, virus scan hook, stored outside the web root.
- Errors and logs never contain tokens, passwords, full provider payloads.
