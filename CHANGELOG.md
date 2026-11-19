# Changelog

All notable changes to **Tayf Studio** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
`0.x` while the product is pre-1.0.

## [Unreleased]

### Added
- Cost dashboard: `GET /api/v1/costs/me` summarizes charged/refunded credits from the append-only ledger, per-stage wall-clock time and provider/model consumption from the verifiable proof trail, and an AR/EN studio panel. Scene credits are attributed to the generation stage (`keyframes` or `video`); legacy jobs that recorded cost on `store` are still supported without a migration.
- Neutral storage layer: job rows and approval reviews now persist provider-neutral object keys; `GET` serialization mints fresh short-lived URLs for local, MinIO, S3, R2 or any S3-compatible backend through one `signed_url` seam. Legacy stored URLs are still resolved on read, so no data migration is needed. `STORAGE_SIGNED_URL_TTL_SECONDS` controls link lifetime and compose now forwards all storage settings to both API and worker.
- Optional human approval gates: jobs created with `require_approvals=true` pause after the storyboard (text/prompt review) and after assets (image or native-video preview). `POST /api/v1/jobs/{id}/approval` approves or rejects; approval resumes from stored bytes without re-calling the provider, rejection refunds through the normal cancel path. Decisions are recorded in `approval_history` and in the proof chain. AR/EN studio review panel and migration `a1b2c3d4e5f6`.
- Verifiable per-stage proof: an append-only, hash-chained trail of inputs, provider/model version, runtime, cost and per-stage verification verdicts. `GET /api/v1/jobs/{id}/proof` returns the canonical document, a public SHA-256 hash and an HMAC authenticity tag; the studio shows an AR/EN proof panel with chain integrity. Migration `f6a8c3e2b4d7`.
- Live job progress over Server-Sent Events: short-lived signed stream tickets, `GET /api/v1/jobs/{id}/events`, persisted `progress`/`stage` fields, and an AR/EN progress bar in the studio (PR #9, merged `aee89ae`).
- `JobProgressEvent` wire schema and migration `e5a9c7b1d3f4` for existing databases.
- Native text-to-video provider (`AI_PROVIDER=replicate_t2v`): real LLM storyboard plus MiniMax H3 Highspeed motion video through Replicate REST; the vendor MP4 is stored directly and no per-scene stills are fabricated.
- Stripe credit top-ups: fixed server-owned packages, `POST /payments/topup/checkout-session` and a signed `POST /webhooks/stripe` that grants credits exactly once via the append-only ledger (PR #11, merged `ace0dac`; CI `44273690313` — 184 passed, 82.24%).
- Optional external moderation seam (`MODERATION_API_URL`): prompts and AI-produced text are screened beside the local blocklist; transport errors and malformed verdicts reject by default (PR #12, CI `44281037955` — 197 passed, 82.57%).
- Google-grade repository polish: `Makefile`, pre-commit hooks, CODEOWNERS, issue/PR templates, and a MkDocs documentation site with Development, Architecture, Runbook and Threat Model pages.
- CI quality gates: Python 3.11/3.12/3.13 backend matrix, scoped `mypy` lane, pre-commit and docs workflows, and failure artifacts. `pip-audit` remains the enforced dependency gate; GitHub Dependency Graph is a manual repo setting and is not assumed.

### Security
- SSE uses a 5-minute HMAC capability ticket bound to one user and one job; native `EventSource` never needs the Bearer token in the URL.
- Replicate output downloads are accepted only from `replicate.delivery` hosts, with container sniffing and a configurable size cap.
- Stripe webhooks are accepted only with a valid `v1` HMAC signature (raw body, 5-minute tolerance) and a paid session whose amount, currency and package match a server-side package; duplicate deliveries cannot double-grant credits.
- External moderation is fail-closed: an unavailable service blocks the job with `moderation_unavailable` unless `MODERATION_FAIL_CLOSED=false` is an explicit operator decision.

## [0.6.0] — 2026-11-18

### Added
- Durable job queue: leased claims, heartbeats, stale-job recovery and an external `python -m app.worker` runner (PR #6).
- Atomic job state transitions with guarded refunds and cancellation checkpoints (PR #2).
- Refresh-token registry with SHA-256 digests, rotation, family revocation on reuse and `POST /auth/logout` (PR #7).
- CI coverage gate (80%) plus dependency/SAST scanners: pip-audit, bandit and report-only semgrep.
- `backend/tests/__init__.py` makes local test collection immune to unrelated `tests` packages on `PYTHONPATH`.
- Release workflow for `v*` tags: source archives, SHA-256 checksums, CycloneDX SBOM, build provenance and generated GitHub release notes; `workflow_dispatch` is a build-only dry run.
- Dependabot security updates stay enabled; routine version-update PRs are disabled so dependency changes remain deliberate and reviewed.
- `docs/RELEASING.md` documents the tag checklist, dry run and patch-release policy.

### Security
- Trusted-proxy-only `X-Forwarded-For` parsing closes client-IP spoofing of rate limits (PR #5).
- Refresh tokens are now HttpOnly `SameSite=strict` cookies scoped to `/api/v1/auth`; access tokens live in memory only.
- Default bind addresses fail closed: backend and ai-gateway use loopback unless deployment explicitly exposes them.
- Gateway requires `AI_GATEWAY_TOKEN` on any non-loopback bind; pillow bumped to patched 13.x.

### Changed
- Breaking API: `/auth/refresh` no longer accepts a token in the JSON body; auth responses no longer contain `refresh_token`.
- `TRUSTED_PROXIES` must list every proxy allowed to set `X-Forwarded-For`.
- `docker compose up` now fails fast unless `AI_GATEWAY_TOKEN` is set in `.env`.
- `EXTERNAL_JOB_WORKER=true` in compose; the API leaves jobs `PENDING` for the worker.
- `APP_VERSION` and the version-endpoint test now report `0.6.0`, matching this changelog.
- `main` is protected with strict required checks for the CI matrix, lint, typecheck, pre-commit, security scan, Docker, frontend and GitGuardian; force pushes and branch deletion are disabled.

## [0.5.0] — 2026-11-01

### Added
- **Refresh-token rotation**: `POST /api/v1/auth/refresh` issues a new
  access+refresh pair (30-day refresh lifetime, `JWT_REFRESH_EXPIRES_DAYS`).
  The frontend rotates silently on any 401 and retries the request — sessions
  survive past 2 hours without re-login. Refresh tokens can never authorize
  the API, and access tokens can never refresh.
- **Rate limiting** (in-memory sliding window, zero dependencies):
  register/login/refresh share the `auth` bucket (`RATELIMIT_AUTH_LIMIT`,
  default 10/min/IP) and job creation has its own bucket
  (`RATELIMIT_JOB_LIMIT`, default 30/min/IP). Exceeding the limit returns
  `429` + `Retry-After`. Honors `X-Forwarded-For` behind proxies;
  `RATELIMIT_ENABLED=false` for trusted networks.
- **Signed artifact URLs**: `GET /api/v1/files/*` now requires a short-lived
  HMAC signature (`?exp=&sig=`, 6h TTL, derived from `JWT_SECRET`) —
  "non-guessable UUID" is no longer the only access control. The API mints
  signed URLs when serializing jobs, so the UI needs no changes.
  `FILES_PUBLIC=true` reverts to open URLs for public demos.
- **Job cancellation**: `POST /api/v1/jobs/{id}/cancel` cancels pending/
  processing jobs, refunds charged credits with an auditable
  `refund_job_cancelled` ledger entry, and the pipeline checks cancellation
  cooperatively between stages (after storyboard, between keyframes, after
  composition) so cancelled jobs stop spending provider budget.
- **Prometheus metrics**: `GET /api/v1/metrics` (text/plain; version=0.0.4)
  with `tayf_http_requests_total{method,status}`, `tayf_jobs_total{status}`
  and `tayf_credits_total{kind}`. Aggregate counters only — no user data;
  disable with `METRICS_ENABLED=false`.
- **Credit ledger UI**: collapsible ledger panel in the studio sidebar showing
  every movement (charge/refund/bonus) with the running balance.
- **Cancel button** on pending/processing job cards.
- **Language persistence**: AR/EN choice survives reloads
  (`localStorage`, synced to `<html lang/dir>`).
- **Production containers**: `backend/Dockerfile` (multi-stage, non-root,
  ffmpeg included, healthcheck, alembic on boot), `frontend/Dockerfile`
  (Vite build + unprivileged nginx 8080 with SPA fallback and same-origin
  `/api` proxy + hardened caching), `ai-gateway/Dockerfile`. Compose stack
  rebuilt around them with a `tayf-data` volume and **mandatory** `JWT_SECRET`
  (the stack refuses to boot with a placeholder secret).
- **Lint + image CI**: `ruff` (E/F/W/B, bug-focused scope) added with config
  in `pyproject.toml`, a CI lint job, and a job that builds all three Docker
  images on every push/PR (the trigger block was verified byte-identical —
  `branches: [main]` was always correct on disk; an earlier display artifact
  in this environment briefly suggested otherwise and is disproved by `od -c`).
- `SECURITY.md` and `CODE_OF_CONDUCT.md`.

### Fixed
- 6 unused imports and one unused loop variable removed (ruff-audited).

> توثيق: تقرير سابق في هذا السجل لمّح إلى أن مرشّح فروع CI كان مكسورًا
> (`branches: ain]`) — الفحص البايتي بـ `od -c` أثبت أن الملف سليم دائمًا
> على القرص (`[main]`) وأن ما رُصد كان تشويه عرض في نقل مخرجات Bash فقط.

### Changed
- Rate-limit config defaults in `.env.example`; `JWT_REFRESH_EXPIRES_DAYS`,
  `FILES_PUBLIC`, `METRICS_ENABLED` documented there.
- `docker-compose.yml` rewritten from dev-style stock images to the built
  production images.

## [0.4.1] — 2026-10-31

### Added
- Security hardening middleware on **every** response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy`
  (pure-ASGI implementation, no new dependencies).
- Request observability: `X-Request-ID` propagation (client IDs validated and
  sanitized) + one structured access-log line per request.
- `GET /api/v1/version` — build & runtime info (version, Python, storage backend,
  AI provider); the frontend footer displays the live version chip.
- Auth landing: value bullets (honesty / auditable credits / safety) + loading
  skeleton + visual polish layer (sticky topbar, status rails, reduced-motion support).
- `docs/ENGINEERING_REVIEW.md` — full engineering evaluation, competitive scan
  and a measurable 90-day roadmap.
- `CONTRIBUTING.md` and this changelog.

### Fixed
- CI workflow trigger now explicitly targets `main` (`branches: [main]`).

## [0.4.0] — 2026-10-31

### Added
- Full generation pipeline: safety screen → credits charge → background job
  (storyboard → keyframes → real MP4 composition via ffmpeg: zoompan + xfade +
  watermark) → storage → credits refund on failure.
- Content-safety screening before and after generation (`core/safety.py`).
- Provider abstraction with three backends: `mock` (clearly SIMULATED),
  `zai_gateway` (real, bundled sidecar), `openai_compatible` (bring your own key).
- Storage abstraction: local filesystem or any S3-compatible store, with TTL
  cleanup loop.
- Frontend studio: projects sidebar, job list with live polling, storyboard and
  video playback, simulated/real badges, AR/EN + RTL-first dark UI.
- Real-generation evidence: LLM storyboard + keyframes + MP4 archived with
  `simulated=false` artifacts.

## [0.3.0] — 2026-10-31

### Added
- Projects API: schema, CRUD endpoints, ownership isolation (404 semantics,
  never 403) and repository-level tests.
- CI: backend pytest + frontend typecheck/build on push and PR.
- Swagger/OpenAPI published on `/docs`.

## [0.2.0] — 2026-10-31

### Added
- SQLite-first data model with UUID keys: `User`, `Project`, `GenerationJob`,
  `CreditLedger`; Alembic migrations with upgrade/downgrade proof.
- Auth core: Argon2id hashing + JWT; append-only credit ledger with signup bonus.

## [0.1.0] — 2026-10-31

### Added
- Running skeleton: FastAPI health endpoint + React/Vite/TypeScript frontend,
  proven end-to-end in a real browser (zero console errors).
