# TASK_TRACKER — VisionForge Studio

> Single source of truth for project status. Read this first after any context
> reset. Statuses allowed: `NOT_STARTED` · `IN_PROGRESS` · `IMPLEMENTED` ·
> `TESTED` · `BLOCKED`.
> Rule: `TESTED` requires a command that was actually run and its real output.

**Last updated:** 2026-10-30 · **Stage reached:** 1 (skeleton) — awaiting review

---

## Current phase

| # | Area | State |
|---|------|-------|
| 0 | Audit & environment | TESTED |
| 1 | Running skeleton (backend + frontend + proxy) | TESTED |
| 2+ | Everything else | NOT_STARTED (blocked on user review) |

---

## Board

| ID | Phase | Task | Status | Acceptance criteria | Evidence / Risks |
|----|-------|------|--------|---------------------|------------------|
| T-00 | 0 | Audit current state + environment (Termux) | TESTED | Written report with proven vs suspected issues | `docs/AUDIT_PHASE_0.md` |
| T-01 | 1 | Repo skeleton, .gitignore, .env.example, git init | TESTED | Clean tree, no secrets tracked | `git log` / `.gitignore` |
| T-02 | 1 | Backend `GET /api/v1/health` + env-driven config | TESTED | 200 JSON, no config leakage | `pytest` → 4 passed |
| T-03 | 1 | Frontend React+Vite+TS page with server-check button | TESTED | Click shows real backend payload | `npm run build` OK |
| T-04 | 1 | Real browser E2E (Chromium + CDP) | TESTED | Button click → success text + payload, 0 JS errors | `scripts/e2e_smoke.py` → PASS |
| T-05 | 1 | README run instructions + one-command dev script | TESTED | Fresh shell can start both servers | `scripts/dev.sh` |
| T-06 | 2 | Architecture decision record (ADR) + data-flow diagram | IN_PROGRESS | Documented boundaries, justified stack choices | `docs/ARCHITECTURE.md` |
| T-07 | 3 | Database schema + Alembic migrations (Users, Projects, GenerationJobs, CreditLedger, …) | NOT_STARTED | Migrations apply + rollback; integrity tests | Needs Postgres — **not installed on this device** |
| T-08 | 4 | API layer (auth, projects, generations, videos, billing, health) | NOT_STARTED | Contract + negative tests green | Depends on T-07 |
| T-09 | 5 | Auth: Argon2id, JWT/refresh rotation, rate limits, RBAC | NOT_STARTED | Auth + authorization test suite green | Depends on T-08 |
| T-10 | 6 | Frontend screens (15 screens), i18n AR/EN, RTL, a11y | NOT_STARTED | Core flows usable against real API | Tailwind + router + state lib not added yet |
| T-11 | 7 | Provider abstraction + capability registry + one real provider | NOT_STARTED | Real credential test OR documented blocker | **No provider credentials available** — mock must stay dev-only |
| T-12 | 8 | Job lifecycle + worker + WebSocket updates + reconnect | NOT_STARTED | Job state survives worker restart; WS resubscribe proven | Redis present locally; no Postgres/Celery yet |
| T-13 | 9 | Credits/billing ledger, idempotency, refunds, webhooks | NOT_STARTED | Concurrency + duplicate-charge tests green | Depends on T-07/T-08 |
| T-14 | 10 | Performance: indexes, pagination, rate limits, load test | NOT_STARTED | Measured numbers documented | No load tool installed yet |
| T-15 | 11 | Full test pyramid (unit→E2E→security→load) | NOT_STARTED | All mandatory cases run, results recorded | — |
| T-16 | 12 | Docker, CI, deploy, monitoring, backups, runbook | NOT_STARTED | Clean-env deploy + health checks | **Docker not installed on this device** |

---

## Decisions taken so far

1. **Stage-1 scope is deliberately tiny** — one endpoint, one screen, proven end
   to end. No DB/auth/provider code before this skeleton is approved.
2. **No venv on this device:** Termux Python 3.14 already ships FastAPI,
   Pydantic, SQLAlchemy, Alembic, pytest. A venv cannot install `pydantic-core`
   (no cp314 Android wheel → Rust source build). `requirements.txt` still exists
   so other machines can install normally.
3. **TypeScript pinned to 5.9** — TS 7 ships a native compiler with no
   `android-arm64` binary (`Unable to resolve @typescript/typescript-android-arm64`).
4. **Vite dev proxy** (`/api` → `127.0.0.1:8000`) is the single origin the
   browser sees; CORS is only configured for direct calls.
5. **Honesty is a UI feature:** the page states in both languages that only the
   connection check exists — no fake generation.

## Known gaps / risks

- No Postgres, no Docker on this phone → Stages 3 and 12 need either
  `pkg install postgresql` (or a remote DB) and a documented alternative.
- No AI provider credentials → Stage 7 cannot be proven live yet.
- Redis exists but no worker queue is wired.

## NOW

Stage 1 is verified and the servers are running locally. **Waiting for user
review of the skeleton before starting Stage 2 (database).**
