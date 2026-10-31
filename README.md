# Tayf Studio

**AI video generation studio — Arabic-first (AR/EN).** Describe a scene, get a
real storyboard, real keyframes, and a real MP4 — with an auditable credit
system and a safety layer. Built stage by stage, with the proof for every stage
recorded in `TASK_TRACKER.md`.

**Status: Unified Studio (v0.4).** The VisionForge feature line merged into the
Tayf data model: real auth, credits, storage, safety, provider abstraction and
a full generation pipeline. Nothing here pretends — mock output is stamped
`SIMULATED`, real providers are flagged real, failures refund your credits.

[![CI](https://github.com/tibatechapp-ship-it/tayf/actions/workflows/ci.yml/badge.svg)](https://github.com/tibatechapp-ship-it/tayf/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What actually works (all verified by real tests)

| Piece | Evidence |
|---|---|
| Register / login / me — Argon2id + JWT | `tests/test_auth.py` |
| Projects CRUD with ownership isolation (404, never 403) | `tests/test_api_projects.py`, `tests/test_project_crud.py` |
| Jobs: safety screen → credits → background pipeline | `tests/test_jobs…` via `test_pipeline.py` |
| Real MP4 composition (ffmpeg: zoompan + xfade + watermark) | `tests/test_compose.py` (real `ftyp` MP4s) |
| Credits: append-only ledger, signup bonus, refunds | `tests/test_credits.py` |
| Storage: local filesystem or any S3-compatible store + TTL cleanup | `tests/test_storage.py`, `tests/test_files.py` |
| Content safety: pre/post generation screening | `tests/test_safety.py` |
| Migrations: upgrade / downgrade / model-drift guard | `tests/test_migrations.py` |
| **Backend suite** | `pytest` → **95 passed** |
| Frontend: React 19 + Vite 8 + TS strict | `npm run build` clean |
| **Browser E2E**: register → project → job → completed video | `scripts/e2e_smoke.py` → `RESULT: PASS`, 0 JS errors |
| **Real AI generation** (LLM storyboard + real keyframes + MP4) | see `docs/AI_PROVIDERS.md` — `simulated=false` artifacts archived |

## Requirements

- Python 3.11+ — `pip install -r backend/requirements-dev.txt`
  - **Termux:** plain `uvicorn` (no uvloop); `pkg install ffmpeg` is required
    for video composition; if `argon2-cffi`/`pillow` fail to build:
    `pkg install clang python-pillow`
- Node 20+ — TypeScript pinned to 5.x (TS 7 has no android-arm64 build)
- No Postgres needed: the default `DATABASE_URL` is SQLite.

## Run

```bash
cp .env.example .env            # optional; defaults work
./scripts/dev.sh start          # alembic upgrade head + API :8000 + UI :5173
./scripts/dev.sh status
```

Open <http://127.0.0.1:5173>, create an account (you get 100 credits), create
a project, and generate. The default `mock` provider works with zero keys and
every artifact is clearly marked SIMULATED.

### Real generation (two options)

```bash
# Option A: the bundled gateway sidecar (real LLM + real image model)
./scripts/dev.sh gateway        # sidecar on 127.0.0.1:3030
# then set in .env:  AI_PROVIDER=zai_gateway

# Option B: bring your own key (any OpenAI-compatible API)
#   AI_PROVIDER=openai_compatible
#   OPENAI_BASE_URL=...  OPENAI_API_KEY=...
```

Details and the honesty matrix: `docs/AI_PROVIDERS.md`.

## Verify (what the tracker cites)

```bash
cd backend && python -m pytest -v          # 95 passed
cd frontend && npm run build               # typecheck + bundle
./scripts/run_e2e.sh                       # full browser loop -> RESULT: PASS

# schema proof
cd backend && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## Switching to PostgreSQL

The schema is engine-neutral (`sa.Uuid`, `sa.JSON`, VARCHAR+CHECK enums):

```bash
# .env
DATABASE_URL=postgresql+psycopg://tayf:secret@localhost:5432/tayf
pip install "psycopg[binary]"
cd backend && alembic upgrade head
```

## API

| Method | Path | Status |
|---|---|---|
| GET | `/api/v1/health` | implemented |
| POST | `/api/v1/auth/register` → `201` token + 100 credits | implemented |
| POST | `/api/v1/auth/login` → `200` token | implemented |
| GET | `/api/v1/auth/me` | implemented (JWT) |
| GET/POST | `/api/v1/projects` | implemented (JWT) |
| GET/PATCH/DELETE | `/api/v1/projects/{id}` | implemented (DELETE = archive) |
| POST | `/api/v1/projects/{id}/jobs` → `202` | implemented (402 on low balance) |
| GET | `/api/v1/projects/{id}/jobs`, `/api/v1/jobs/{id}` | implemented |
| GET | `/api/v1/credits/me` | implemented (balance + ledger) |
| GET | `/api/v1/files/{key}` | implemented (local serve / S3 presign) |
| GET | `/docs`, `/openapi.json` | implemented (FastAPI) |

## Layout

```
backend/app/
  main.py                 FastAPI app + TTL cleanup lifespan
  api/deps.py             JWT bearer dependency
  api/v1/endpoints/       auth, projects, jobs, credits, files
  core/                   config (.env), security (Argon2id+JWT), safety
  db/session.py           engine factory, SQLite FK+WAL pragmas
  models/                 Base + mixins, User, Project, GenerationJob, CreditLedger
  repositories/           user, project, job (ownership enforced at query level)
  schemas/                pydantic wire contracts
  services/ai/            base contract + mock | zai_gateway | openai_compatible
  services/               credits (ledger), pipeline, compose (ffmpeg)
  services/storage/       base + local + s3 + factory, TTL cleanup
  migrations/             Alembic: a347dd0c8c67 -> c3d9e5f81a42
ai-gateway/               Node sidecar: real LLM + real image model (localhost only)
frontend/src/             React 19 + Vite 8, AR/EN i18n, RTL-first dark UI
scripts/                  dev.sh (start/gateway/stop/status), run_e2e.sh, e2e_smoke.py
docs/                     ARCHITECTURE, DATA_MODEL, AI_PROVIDERS, AUDIT_PHASE_0
```

## Non-negotiable rules (inherited from the project charter)

1. No fabricated success — every claim above has a test or artifact behind it.
2. Simulated output is **always labeled** (`simulated=true` → UI badge + stamp).
3. Secrets live only in `.env` (never committed); production requires `JWT_SECRET`.
4. Runs on Termux/low-resource machines — no compiled-only deps, plain uvicorn.
5. `TASK_TRACKER.md` is the single source of truth for status.
