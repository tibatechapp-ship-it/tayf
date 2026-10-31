# Tayf

AI video generation studio — Arabic-first (AR/EN). Built stage by stage, with
the proof for every stage recorded in `TASK_TRACKER.md`.

**Status: Stage 2 — data model + migrations + repositories.**
There is still **no video generation, no auth, and no public API** beyond
`GET /api/v1/health`. The UI says so out loud; nothing here pretends otherwise.

---

## Verified today

| Piece | Evidence |
|---|---|
| `GET /api/v1/health` | `pytest` (health contract suite) + `curl` → 200 |
| Browser → Vite proxy → FastAPI | `scripts/e2e_smoke.py` → `RESULT: PASS`, 0 JS errors |
| 3 tables (users, projects, generation_jobs) with UUID PKs, CHECK enums, cascades | `alembic upgrade head` + DDL dump in `docs/DATA_MODEL.md` |
| Migration rollback | `alembic downgrade base` → re-upgrade, suite passes |
| Models ↔ migrations cannot drift | `compare_metadata()` test → no diff |
| Owner isolation | `test_project_crud.py` (other user gets `None`, cascade proven from a fresh session) |
| Backend suite | `pytest` → **33 passed in 2.13s** |
| Frontend build | `npm run build` → tsc clean + 70.22 kB gzip |

## Requirements

- Python 3.11+ with `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`,
  `sqlalchemy`, `alembic`, `pytest`, `httpx`
  - **Termux note:** already installed system-wide here; a venv cannot build
    `pydantic-core` on Python 3.14. Elsewhere:
    `python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt`
- Node 20+ (here 26) — TypeScript is pinned to **5.x** (TS 7 has no android-arm64 build)
- No Postgres needed for development: the default `DATABASE_URL` is SQLite.

## Run

```bash
cd tayf
cp .env.example .env          # optional; defaults work

./scripts/dev.sh start        # runs alembic upgrade head, then API :8000 + UI :5173
./scripts/dev.sh status
./scripts/dev.sh stop
```

Open <http://127.0.0.1:5173> and press **فحص اتصال الخادم**.

## Verify (what the tracker cites)

```bash
cd backend && python -m pytest -v        # 33 passed
cd frontend && npm run build             # typecheck + bundle
python scripts/e2e_smoke.py http://127.0.0.1:5173 /tmp/tayf.png   # RESULT: PASS

# schema proof
cd backend && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## Switching to PostgreSQL

The schema is engine-neutral (`sa.Uuid`, `sa.JSON`, VARCHAR+CHECK enums), so it
is a URL change plus one command — not a rewrite:

```bash
# .env
DATABASE_URL=postgresql+psycopg://tayf:secret@localhost:5432/tayf
pip install "psycopg[binary]"
cd backend && alembic upgrade head
```

Nothing else changes: repositories and models contain no SQLite-specific code
(the only pragma is guarded to SQLite connections).

## Layout

```
backend/
  app/main.py                     FastAPI app (health only)
  app/core/config.py              pydantic-settings (.env, DATABASE_URL, CORS)
  app/api/v1/health.py            the health contract
  app/models/                     Base + mixins, User, Project, GenerationJob, enums
  app/db/session.py               engine factory, SQLite FK pragma, session dependency
  app/repositories/               user_repository, project_repository (ownership at query level)
  migrations/                     Alembic env + initial schema
  tests/                          health, migrations, users, projects (33 tests)
frontend/src/{App.tsx,services/api.ts,i18n/dictionary.ts}
scripts/dev.sh                    start|stop|status|migrate|logs
scripts/e2e_smoke.py              Chromium+CDP end-to-end proof
docs/                             AUDIT_PHASE_0, ARCHITECTURE, DATA_MODEL
```

## API

| Method | Path | Status |
|---|---|---|
| GET | `/api/v1/health` | implemented |
| GET | `/docs`, `/openapi.json` | implemented (FastAPI) |
| POST | `/api/v1/projects` | implemented — `400` if the owner does not exist |
| GET | `/api/v1/projects?owner_id=&limit=&offset=&include_archived=` | implemented |
| GET | `/api/v1/projects/{id}?owner_id=` | implemented — `404` for missing **or** foreign rows |
| PATCH | `/api/v1/projects/{id}?owner_id=` | implemented — partial update |
| DELETE | `/api/v1/projects/{id}?owner_id=` | implemented — soft delete (`status=archived`), `204` |
| auth / generations / videos / billing | — | **not implemented (Stage 5+)** |

`owner_id` is an explicit parameter **only until Stage 4 adds authentication** —
it exists so ownership isolation can be tested (and attacked) for real.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects \
  -H 'content-type: application/json' \
  -d '{"name":"Launch video","owner_id":"<user-uuid>"}'
```

## Next stage

Stage 5: authentication (Argon2id, access/refresh rotation, rate limits) and the
replacement of the explicit `owner_id` with the token subject. No endpoint is
announced before it has tests — positive and negative.
