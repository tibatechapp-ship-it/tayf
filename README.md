# VisionForge Studio

AI video generation platform — Arabic-first (AR/EN), built stage by stage with
tests at every stage.

**Current status: Stage 1 — running skeleton.** The only working feature is a
frontend ↔ backend health check. There is **no** video generation, **no** user
account and **no** database yet. Nothing here pretends otherwise.

---

## What works right now (verified)

| Piece | Proof |
|---|---|
| `GET /api/v1/health` (FastAPI) | `pytest` → 4 passed; `curl` → 200 JSON |
| React + Vite + TS page with a real "check server" button | `npm run build` OK; browser click test PASS |
| Vite `/api` proxy → backend | `curl 127.0.0.1:5173/api/v1/health` → 200 |
| One-command dev control | `./scripts/dev.sh start` |

## Requirements

- Python 3.11+ with `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`,
  `pytest`, `httpx`
  - **Termux note:** these are already installed system-wide here, and a venv
    cannot build `pydantic-core` on Python 3.14 (no wheel) — use system Python.
  - Anywhere else: `python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt`
- Node 20+ (here: Node 26)
- TypeScript **5.x** is pinned — TS 7 has no `android-arm64` binary

## Run it

```bash
cd visionforge-studio
cp .env.example .env          # optional in dev; defaults already work

./scripts/dev.sh start        # starts backend :8000 + frontend :5173
./scripts/dev.sh status
./scripts/dev.sh stop
```

Then open <http://127.0.0.1:5173> and press **فحص اتصال الخادم**.

Manual alternative:

```bash
# terminal 1
cd backend && python -m uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm install && npm run dev
```

## Verify (the same commands the tracker cites)

```bash
# backend contract tests
cd backend && python -m pytest

# frontend typecheck + production build
cd frontend && npm run build

# real browser proof: click the button, assert the payload, save a screenshot
python scripts/e2e_smoke.py http://127.0.0.1:5173 /tmp/stage1.png
```

Expected tail: `RESULT: PASS`.

## Layout

```
backend/app/{main.py,core/config.py,api/v1/health.py}   # health slice only
backend/tests/test_health.py                            # contract tests
frontend/src/{App.tsx,services/api.ts,i18n/dictionary.ts}
scripts/dev.sh                                          # start|stop|status|logs
scripts/e2e_smoke.py                                    # Chromium+CDP E2E
docs/AUDIT_PHASE_0.md                                   # what exists / what's missing
docs/ARCHITECTURE.md                                    # target architecture + ADRs
TASK_TRACKER.md                                         # single source of truth
```

## Environment variables

See `.env.example`. Nothing is required for development; every later secret
(database URL, JWT secret, provider keys) stays out of git.

## API

| Method | Path | Status |
|---|---|---|
| GET | `/api/v1/health` | implemented |
| GET | `/docs`, `/openapi.json` | implemented (FastAPI) |
| everything else in the plan | — | not implemented |

## Next stage (awaiting review)

Stage 2/3: PostgreSQL schema + Alembic migrations (users, projects, generation
jobs, videos, assets, credit ledger, notifications, API keys, audit log) with
integrity tests. Postgres is **not installed on this device** — it has to be
installed locally or provided as a dev database before that stage can be
verified for real.
