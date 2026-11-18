# Development guide

## Prerequisites

| Tool | Minimum | Notes |
| --- | --- | --- |
| Python | 3.11 | CI matrix: 3.11 / 3.12 / 3.13; 3.14 works locally with caveats |
| Node.js | 20 | npm lockfile is committed; use `npm ci` |
| ffmpeg | any recent build | Required for real MP4 composition; `pkg install ffmpeg` on Termux |
| make | any POSIX make | Optional but recommended |

## One-command bootstrap

```bash
make bootstrap
```

This installs backend dev dependencies, frontend dependencies from
`frontend/package-lock.json`, and the pre-commit hooks.

## Run locally

```bash
cp .env.example .env
make dev                 # scripts/dev.sh start
```

Useful addresses:

- Frontend: `http://127.0.0.1:5173`
- Backend docs: `http://127.0.0.1:8000/docs`
- AI gateway (when started): `http://127.0.0.1:3030/health`

## Verify a change

```bash
make lint          # ruff check — enforced in CI
make typecheck     # mypy (scoped baseline) + frontend strict TS + build
make precommit     # all hooks against the full tree
make test          # pytest matrix with 80% coverage gate
make security      # pip-audit + bandit
make docs-build    # mkdocs build --strict
```

`make ci` runs the local approximation of the full pipeline. CI is still the
authoritative result.

## Local caveats

- `backend/tests/test_credits.py` can hang on Termux/Python 3.14. Run the rest
  locally and let CI execute the full suite.
- Frontend `npm ci` may fail on Termux with `libicui18n.so.78` missing; the CI
  frontend job is authoritative.
- `ruff format --check` is informational, not a CI gate: the repo has
  pre-existing line-length churn. Do not introduce new churn.
- `mypy` checks 53 of 66 backend modules today. Thirteen legacy modules with
  SQLAlchemy/HTTP typing debt are excluded explicitly in `backend/pyproject.toml`;
  shrink that list, never grow it.

## Database migrations

```bash
make alembic-check   # downgrade base → upgrade head → upgrade head
```

When a schema changes, add an Alembic revision and a test in
`backend/tests/test_migrations.py`.

## Adding an AI provider

1. Implement the provider seam in `backend/app/services/ai/base.py`.
2. Register it in `backend/app/services/ai/factory.py`.
3. Add config in `backend/app/core/config.py` and `.env.example`.
4. Document the honesty matrix in `docs/AI_PROVIDERS.md`.
5. Add tests for config validation, network boundaries and output shape.

## Adding user-facing text

All strings visible to users must exist in both `ar` and `en` inside
`frontend/src/i18n/dictionary.ts`. RTL layout is the default; verify both.

## Documentation

```bash
make docs-serve      # http://127.0.0.1:8001
make docs-build      # strict build, same as CI and the Pages workflow
```

## Commit and PR conventions

Use imperative conventional commits: `feat(scope)`, `fix(scope)`, `docs`,
`test`, `ci`, `chore`. Every PR must fill `.github/pull_request_template.md`,
include CI evidence, and update `CHANGELOG.md` plus `TASK_TRACKER.md` when
behavior changes.
