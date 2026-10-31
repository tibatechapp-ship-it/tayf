# Changelog

All notable changes to **Tayf Studio** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
`0.x` while the product is pre-1.0.

## [Unreleased]

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
