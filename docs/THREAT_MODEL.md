# Threat model

## Assets

| Asset | Why it matters |
| --- | --- |
| User accounts and sessions | Impersonation enables credit theft and data access |
| Credit ledger | Financial source of truth; append-only audit trail |
| Generation jobs and prompts | May contain sensitive or disallowed content |
| Artifacts | Generated media stored with signed URLs |
| Provider and payment keys | Direct financial and quota impact |

## Trust boundaries

```
Browser ──HTTPS──▶ nginx ──same-origin /api──▶ FastAPI ──▶ services ──▶ repositories ──▶ DB
                                                    ├──▶ AI providers (httpx)
                                                    ├──▶ Stripe (webhook)
                                                    ├──▶ Moderator (HTTP)
                                                    └──▶ Storage backend
```

Only the API validates identity. Only repositories issue ownership-scoped
queries. Only services move credits.

## Threats and mitigations

| Threat | Mitigation | Residual risk |
| --- | --- | --- |
| Stolen access token | 120-minute access JWT; memory-only in frontend; refresh tokens HttpOnly + digest registry + replay revocation | Access JWTs are stateless until expiry |
| Client IP spoofing | `TRUSTED_PROXIES` allowlist; rightmost untrusted `X-Forwarded-For` hop | Misconfigured proxy lists defeat the filter |
| Prompt abuse | Local blocklist + optional external moderation; fail-closed on outage | Provider-specific policy gaps; review prompts with care |
| SSRF via provider URL | Fixed vendor hosts; Replicate downloads limited to `replicate.delivery`; no user-supplied fetch URLs | Operator misconfiguration of gateway base URL |
| Credit double-spend | Atomic balance updates; unique `operation_key` per ledger movement | Concurrency outside SQLite/Postgres transaction scope |
| Stripe replay / forgery | Raw-body `v1` HMAC, 5-minute tolerance, paid status + amount/currency/package checks, idempotent grant | Endpoint secret leakage requires immediate rotation |
| Artifact enumeration | Signed short-lived URLs; ownership checks on job reads | `FILES_PUBLIC=true` intentionally disables this |
| Secret leakage | `.env` only, GitGuardian in CI, no secret literals in fixtures | Developer copy/paste mistakes |
| Supply chain compromise | pip-audit, bandit, semgrep, lockfiles, container builds in CI | No pinned action SHAs yet; tracked in the release-hardening backlog |

## Security testing

```bash
make security
```

CI runs the same dependency and SAST checks on every pull request, plus
GitGuardian secret scanning. Security reports go through
[SECURITY.md](https://github.com/tibatechapp-ship-it/tayf/blob/main/SECURITY.md),
never public issues.

## Design decisions

- Fail closed rather than silently allow when moderation cannot be reached.
- Reject rather than guess when a webhook signature or amount cannot be verified.
- Keep the credit ledger immutable: corrections are new rows, not edits.
- Prefer boring dependencies that build on Termux and in minimal containers.
