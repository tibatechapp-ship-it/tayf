# Contributing to Tayf Studio

شكرًا لاهتمامك! المشروع مبني على قواعد غير قابلة للتفاوض — احترمها وسيكون التعاون سهلًا.

## The non-negotiable rules

1. **No fabricated success.** Every claim in a PR description needs a test,
   a command output, or an artifact behind it. "It should work" is not evidence.
2. **Simulated output is always labeled.** Anything produced by a non-real
   provider must carry `simulated=true` end to end (API → UI badge → stamp).
3. **Secrets live only in `.env`** (never committed). Production requires
   `JWT_SECRET`. If a secret ever lands in the repo, treat it as compromised.
4. **Termux/low-resource stays supported.** No compiled-only dependencies
   (plain `uvicorn`, no `uvicorn[standard]`); no heavy frontend frameworks;
   `pkg install ffmpeg` remains the only native requirement for composition.
5. **`TASK_TRACKER.md` is the single source of truth** for status. Update it
   with evidence when you change behavior.

## Dev setup

The supported entry point is the `Makefile`:

```bash
make bootstrap          # backend + frontend + pre-commit hooks
cp .env.example .env
make dev                # http://127.0.0.1:5173 and :8000/docs
```

Manual setup is still available:

```bash
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

cd frontend && npm ci && npm run dev
```

See `docs/DEVELOPMENT.md` for the full command reference and local caveats.

## Before you open a PR — checklist

- [ ] `make lint` — ruff check green.
- [ ] `make test` — pytest green with the 80% coverage gate; tests added/updated.
- [ ] `make typecheck` — strict TypeScript typecheck + bundle clean.
- [ ] `make security` — pip-audit + bandit clean.
- [ ] `make docs-build` — MkDocs strict build clean when docs changed.
- [ ] If you touched the schema: `make alembic-check` passes.
- [ ] If you touched user-facing strings: both `ar` and `en` entries exist in
      `frontend/src/i18n/dictionary.ts`.
- [ ] No secrets, no `print`-debugging, no new heavy dependencies.
- [ ] `CHANGELOG.md` has an entry; `TASK_TRACKER.md` evidence log is updated.

## Commit style

Conventional-ish, imperative: `feat(scope): ...`, `fix(scope): ...`,
`docs: ...`, `test: ...`, `ci: ...`, `chore: ...`.
