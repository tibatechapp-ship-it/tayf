# Security Policy — Tayf Studio

## Supported versions

| Version | Supported |
| --- | --- |
| 0.5.x | ✅ |
| < 0.5 | ❌ (upgrade — 0.5.0 closed the rate-limiting / artifact-URL / session-rotation gaps) |

## Reporting a vulnerability

**Do not open a public issue for security problems.**

1. Use GitHub's *Private vulnerability reporting* on this repository
   (Security tab → Report a vulnerability), **or**
2. Contact the maintainers through the repository owner
   ([tibatechapp-ship-it](https://github.com/tibatechapp-ship-it)).

Include: what you found, how to reproduce it, and (if possible) what a fix
looks like. You will get an acknowledgement within **72 hours** and a status
update at least every 7 days until the issue is resolved. We credit reporters
in the changelog unless they prefer to stay anonymous.

## Security model — what Tayf does (and does not) promise

Implemented and test-backed:

- **Passwords**: Argon2id hashing (`argon2-cffi`), never logged or stored in
  plaintext. Weak/duplicate-password rules enforced at registration.
- **Sessions**: HS256 JWT access tokens (default 120 min) + refresh tokens
  (default 30 days, rotated on every refresh). Refresh tokens cannot authorize
  API routes; access tokens cannot refresh. `JWT_SECRET` is **required** when
  `APP_ENV=production` — the server refuses to start without it.
- **Rate limiting**: sliding-window per-IP limits on
  register/login/refresh (`RATELIMIT_AUTH_LIMIT`) and job creation
  (`RATELIMIT_JOB_LIMIT`) with `429` + `Retry-After`.
- **Artifact access**: `/api/v1/files/*` URLs are HMAC-signed, short-lived
  capability tokens derived from `JWT_SECRET` (`FILES_PUBLIC=false` default).
- **Ownership isolation**: every project/job query is scoped to the caller —
  foreign IDs return `404`, not `403`.
- **Transport-independent defenses**: `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy` on every
  response; validated `X-Request-ID` propagation.
- **Content safety**: pre- and post-generation screening with an extensible
  blocklist (`SAFETY_EXTRA_BLOCKED_TERMS`).
- **Secrets hygiene**: secrets live only in `.env` (never committed);
  CI runs tests with placeholder secrets only.

Honest limits (documented, not hidden):

- No email verification or password reset yet (no SMTP dependency by design) —
  losing your database means losing accounts, losing a password means losing
  that account until an operator intervenes.
- The rate limiter is in-process: it resets on restart and does not span
  replicas. For multi-replica deployments, front the API with a limiter
  (nginx `limit_req`, Cloudflare, or swap the store for Redis).
- JWTs are stateless: there is no server-side revocation list. Rotate
  `JWT_SECRET` to invalidate all sessions at once.
- Deployment transport (TLS) is a proxy concern — terminate HTTPS at nginx or
  your cloud load balancer.

## Known-good configuration checklist (production)

```env
APP_ENV=production
JWT_SECRET=<64+ hex chars — generate, never reuse>
RATELIMIT_ENABLED=true
FILES_PUBLIC=false
CORS_ORIGINS=https://your-domain.example
```

- Terminate TLS in front of the stack (the bundled nginx serves plain HTTP on 8080).
- Set `DATABASE_URL` to PostgreSQL for real deployments (SQLite stays for dev/Termux).
- Back up the credit ledger (`credit_ledger` table) — it is append-only and audit-grade.
