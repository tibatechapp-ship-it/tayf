# Al-Manazir Engineering

Al-Manazir is an Arabic-first AI video generation platform: FastAPI + React/TypeScript,
portable SQLite by default, and a provider seam that distinguishes honest
simulation from real vendor output.

## Principles

1. **Evidence over claims.** Every shipped change has tests, CI output, or an artifact behind it.
2. **Honest output.** `simulated=true` is propagated from provider to UI; never fabricate media.
3. **Fail closed on safety.** External moderation rejects when its verdict cannot be trusted.
4. **Termux stays supported.** Plain `uvicorn`, no compiled-only convenience packages.
5. **The ledger is audit-grade.** Every credit movement is append-only and tied to a job or payment.

## Start here

| Goal | Document |
| --- | --- |
| Set up a development environment | [Development](DEVELOPMENT.md) |
| Understand the system boundaries | [Architecture](ARCHITECTURE.md) |
| Operate production safely | [Runbook](RUNBOOK.md) |
| Review trust boundaries and risks | [Threat model](THREAT_MODEL.md) |
| Choose an AI provider | [AI providers](AI_PROVIDERS.md) |
| Inspect the persistence model | [Data model](DATA_MODEL.md) |

## Current verified state

- Backend: **197 passed**, coverage **82.57%** (CI `44281037955`).
- Frontend: strict TypeScript typecheck + Vite production build green.
- Security: pip-audit, bandit, semgrep (report-only), GitGuardian green.
- Delivery: SSE progress, durable worker queue, native Replicate T2V, Stripe top-ups and external moderation merged on `main`.
