# ADR 0001 — Current architecture

Status: **Accepted** · Date: 2026-11-18

## Context

Tayf began as a FastAPI + React prototype. By late 2026 it carried real user
accounts, a credit ledger, provider integrations, a queue, payments and
moderation. The architecture docs still described several of these as "planned",
which made it hard to reason about current behavior and risk.

## Decision

We record the currently shipped architecture as the baseline:

- FastAPI API with explicit layers: `api → services → repositories`.
- Leased job queue with an external worker (`python -m app.worker`).
- SSE progress backed by short-lived HMAC tickets, with 4-second polling fallback.
- Provider seam with `mock`, `zai_gateway`, `openai_compatible` and `replicate_t2v`.
- Append-only credit ledger with unique `operation_key` idempotency.
- Stripe Checkout + signed webhook fulfillment.
- Local blocklist plus optional external moderation, fail-closed by default.
- MkDocs as the canonical engineering documentation surface.

## Consequences

Positive:

- Documentation matches shipped behavior and CI evidence.
- New contributors get one deterministic command surface (`make`).
- Security and operations have explicit runbooks and a threat model.

Negative / follow-up:

- `ruff format --check` remains informational because of pre-existing churn.
- Type checking is scoped to critical pure modules until broader cleanup.
- GitHub Actions are not yet SHA-pinned; supply-chain hardening is a later batch.

## Alternatives considered

- Rewriting the backend around a task framework: rejected; the leased queue is
  already proven and keeps Termux support.
- Moving docs to a separate site: rejected; MkDocs keeps docs next to code and
  enables a strict CI gate.
