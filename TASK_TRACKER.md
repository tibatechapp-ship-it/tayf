# TASK_TRACKER — Tayf

> Single source of truth. Read this first after any context reset.
> Statuses: `NOT_STARTED` · `IN_PROGRESS` · `IMPLEMENTED` · `TESTED` · `BLOCKED`.
> `TESTED` = a command was actually run and its real output is quoted below.

**Last updated:** 2026-10-31 · **Reached:** Stage 2 (data model) — awaiting review

---

## Board

| ID | Phase | Task | Status | Acceptance criteria | Evidence |
|----|-------|------|--------|---------------------|----------|
| T-00 | 0 | Audit state + environment | TESTED | Written report, proven vs suspected | `docs/AUDIT_PHASE_0.md` |
| T-01 | 1 | Repo skeleton, .gitignore, .env.example, git | TESTED | Clean tree, no secrets | `git log` |
| T-02 | 1 | `GET /api/v1/health` + env config | TESTED | 200 JSON, no config leakage | `pytest` health suite |
| T-03 | 1 | React+Vite+TS UI with server-check button | TESTED | Real payload rendered | `npm run build` |
| T-04 | 1 | Browser E2E (Chromium+CDP) | TESTED | Click → success text + payload, 0 JS errors | `scripts/e2e_smoke.py` → PASS |
| T-05 | 1 | `dev.sh` one-command run | TESTED | Fresh shell starts both servers | `dev.sh start` |
| T-06 | 0.5 | Rename project to **Tayf** (`~/tayf`) | TESTED | No stale brand left, history kept | `grep -ri visionforge` → handled |
| T-07 | 2 | `docs/ARCHITECTURE.md` + ADR table | TESTED | Boundaries + justified decisions | doc exists |
| T-08 | 2 | SQLAlchemy models: User, Project, GenerationJob | TESTED | UUID PK, timestamps, enums, relationships | `test_project_crud.py` / mapping smoke |
| T-09 | 2 | Alembic migrations (upgrade / downgrade / re-upgrade) | TESTED | Clean both directions, models↔migrations no drift | `test_migrations.py` (3 tests) |
| T-10 | 2 | Repositories (owner-scoped) | TESTED | No cross-user read; pagination clamped | `test_project_crud.py` |
| T-11 | 2 | Integration tests + isolation fixtures | TESTED | 33 passed, per-test SQLite file | `pytest` → 33 passed in 2.13s |
| T-12 | 3 | Request/response schemas (Pydantic) + pagination envelope | NOT_STARTED | Validation + error contract | depends on T-11 ✅ |
| T-13 | 4 | Project API (`/projects` CRUD) on the repositories | NOT_STARTED | Ownership + negative tests green | depends on T-12 |
| T-14 | 5 | Auth: Argon2id, access/refresh rotation, rate limits | NOT_STARTED | Auth/authorization suite green | needs `argon2-cffi` (no wheel risk — pure C build) |
| T-15 | 6 | Full frontend (15 screens), router, state, i18n | NOT_STARTED | Core flows on real API | Tailwind/router/state lib not added |
| T-16 | 7 | Provider abstraction + capability registry + real provider | BLOCKED | Real credential test OR documented blocker | **no provider credentials** |
| T-17 | 8 | Jobs worker + WebSocket + reconnect/replay | NOT_STARTED | State survives worker restart | Redis present, no queue code |
| T-18 | 9 | Credits ledger, idempotency, refunds, payment webhooks | NOT_STARTED | Concurrency + duplicate-charge tests | depends on T-13 |
| T-19 | 10 | Performance: real measurements, indexes from evidence, load test | NOT_STARTED | Numbers documented | no load tool installed |
| T-20 | 11 | Full suite incl. security + load | NOT_STARTED | Mandatory cases executed | — |
| T-21 | 12 | Docker/CI/deploy/monitoring/backups/runbook | NOT_STARTED | Clean-env deploy + health checks | **Docker missing on device** |
| T-22 | 12 | GitHub repo + CI workflow | BLOCKED | Green run on push | repo `tibatechapp-ship-it/tayf` (private) pushed; run 41137952817 failed in 3s — GitHub annotation: *"job was not started because recent account payments have failed or your spending limit needs to be increased"* → private-repo Actions billing wall, **not code**. Local equivalents pass: `pytest` 33, `npm ci && npm run build` OK. Fix = make the repo public (free minutes) or add billing. |

---

## Decisions (append-only)

1. **Name: Tayf** (طيف) — short, distinctive, Arabic-first, usable as a
   package/repo name. Directory `~/tayf`, service id `tayf-backend`.
2. **SQLite now, PostgreSQL later.** Chosen because Postgres is not installed on
   this phone and the user asked for a small, runnable repo. Mitigation for the
   portability risk: `sa.Uuid` PKs, `sa.JSON`, VARCHAR+CHECK enums, no raw SQL,
   no engine-specific query, `render_as_batch` for SQLite ALTERs, and the
   `DATABASE_URL` switch documented in the README.
3. **UUID primary keys everywhere** — id generation without a central sequence;
   no id enumeration in the API; merge-safe.
4. **Ownership is enforced in the repository query**, not in the caller:
   `get_project_by_id_and_owner()` returns `None` for missing *and* foreign rows.
5. **Stage-2 job statuses are the requested four** (`pending`, `processing`,
   `completed`, `failed`); Stage 8 extends them by migration.
6. **`update_last_login()` required a column**, so `users.last_login_at` was
   added (nullable, UTC).
7. **A test asserts `compare_metadata()` is empty**, so a model edit without a
   migration fails CI instead of surfacing in production.
8. **Cascade is proven at the DB level** (fresh session), because the ORM
   identity map can lie about a row that was deleted underneath it.

## Known gaps / risks

- SQLite is not the production engine: no row-level locks, weaker concurrency.
  Credit settlement (T-18) **must** be designed for Postgres semantics even while
  developed on SQLite (transaction + `SELECT … FOR UPDATE` shape, tested there).
- No Docker → the deploy stage cannot be verified on-device.
- No provider credentials → T-16 stays blocked; a dev mock will be labelled.
- Frontend still has no router/state/Tailwind (Stage 6).

## NOW

Repo: https://github.com/tibatechapp-ship-it/tayf (private). Awaiting a decision on visibility → CI is blocked on private repos for this account.

Stage 2 is complete and verified (33 tests green, migration cycle clean).
**Waiting for review of the data model before building schemas + the public API
(Stage 3/4).**
