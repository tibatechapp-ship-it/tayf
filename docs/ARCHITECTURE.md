# Architecture — Tayf Studio (unified build, v0.4)

Status: **implemented and tested.** The components below exist in the repo and
are covered by the backend suite (95 tests) and the browser E2E. The planned
next stage (dedicated workers, WebSocket progress, payments) is marked as such.

## 1. Component map (as running today)

```
┌──────────────┐   same-origin /api    ┌──────────────────────────────┐
│  Browser     │ ────────────────────▶ │ Vite dev server / reverse    │
│  React 19+TS │ ◀──────────────────── │ proxy (TLS in production)    │
└──────────────┘                       └───────┬──────────────────────┘
                                               │ /api
                                     ┌─────────▼─────────┐
                                     │ FastAPI (app)     │  api → services → repositories
                                     │ JWT auth, CORS    │
                                     └──┬──────┬──────┬──┘
              background tasks (async) │      │      │
                  ┌────────────────────┘      │      └────────────┐
        ┌─────────▼──────────┐   ┌────────────▼─────────┐  ┌──────▼──────────────┐
        │ Pipeline runner    │   │ SQLite (dev) /       │  │ Storage backend     │
        │ storyboard→frames  │   │ PostgreSQL (prod)    │  │ local fs | S3 API   │
        │ →ffmpeg→storage    │   │ via DATABASE_URL     │  │ + TTL cleanup loop  │
        └─────────┬──────────┘   └──────────────────────┘  └─────────────────────┘
                  │
        ┌─────────▼──────────────┐
        │ AI provider (pluggable)│   mock (offline, SIMULATED)
        │ services/ai/base.py    │─── zai_gateway → ai-gateway sidecar :3030
        └────────────────────────┘   openai_compatible (bring your own key)
```

The `ai-gateway` sidecar is a tiny Node process bound to **127.0.0.1 only**
(never exposed); the backend reaches it over loopback with an optional shared
token header.

## 2. Layer boundaries (enforced by directory layout)

| Layer | Location | Rule |
|---|---|---|
| HTTP | `backend/app/api/` | validation + status codes only; no SQL, no business rules |
| Business | `backend/app/services/` | pricing, job lifecycle, refunds, provider calls |
| Persistence | `backend/app/repositories/` | the only place with queries/ORM; ownership is enforced here |
| Models/schemas | `models/`, `schemas/` | DB tables vs wire contracts, kept separate |
| Providers | `backend/app/services/ai/` | one adapter per vendor behind one interface |
| Storage | `backend/app/services/storage/` | `put/get/exists/delete/iter` + TTL cleanup behind one interface |
| Frontend | `frontend/src/{views,services,i18n,styles}` | components never contain business rules; zero mock data |

## 3. Data flow: a generation request (implemented)

1. `POST /projects/{id}/jobs` → JWT → project ownership check.
2. **Safety pre-filter** screens the prompt; a rejection writes a `rejected`
   job row and charges nothing.
3. **One transaction**: insert `pending` job row → `flush()` to get its id →
   ledger `job_charge` entry carrying that id → commit.
4. `202 Accepted` with the job contract; a Starlette background task runs the
   pipeline after the response is sent (works identically under uvicorn and
   TestClient, which makes the suite deterministic).
5. Pipeline (`services/pipeline.py`), committing after every step so polling
   shows live progress:
   `processing → storyboard (provider) → safety screen of AI text → keyframes
   per scene (stored) → ffmpeg MP4 compose (thread) → post-artifact check →
   `completed` (result_url + thumbnail + storyboard JSON)`.
6. Any failure ⇒ `failed` + **full refund** ledger entry. The mock provider is
   the only one allowed to set `simulated=true`.
7. Storage artifacts live under `jobs/<job_id>/…` with a TTL cleanup loop
   (`STORAGE_TTL_DAYS`, default 7) running inside the app lifespan.

## 4. Concurrency model (and its honest limits)

- Background tasks run on uvicorn's event loop; CPU-bound ffmpeg work is moved
  to threads (`asyncio.to_thread`), provider I/O is async httpx.
- SQLite WAL keeps reads flowing while a job writes; `PRAGMA foreign_keys=ON`
  is set on every connection (CASCADE delete actually cascades).
- **Limit:** one process, in-process queue. The moment the owner outgrows a
  single box, the pipeline call site (`background_tasks.add_task(...)`) is the
  only thing to swap for a real worker/queue — everything else stays.

## 5. Next stages (planned, not built — no pretending)

- WebSocket/SSE live progress instead of 4 s polling.
- Dedicated worker process + queue for multi-machine scale.
- A real **video** provider (text-to-video model) behind the same interface —
  today's real output is storyboard + keyframes + composed MP4.
- Payments (top-up packages) on top of the existing ledger.
- Rate limiting + moderation API integration alongside the local term list.
