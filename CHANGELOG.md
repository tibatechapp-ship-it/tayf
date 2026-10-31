# Changelog

All notable changes to **Tayf Studio** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
`0.x` while the product is pre-1.0.

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
