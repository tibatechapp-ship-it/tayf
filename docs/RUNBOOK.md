# Operations runbook

## Service topology

| Component | Default bind | Purpose |
| --- | --- | --- |
| FastAPI backend | `127.0.0.1:8000` | API, scheduler entrypoint, SSE |
| Worker | internal | Claims leased jobs when `EXTERNAL_JOB_WORKER=true` |
| Frontend / nginx | `0.0.0.0:8080` in container | SPA + same-origin `/api` proxy |
| AI gateway | `127.0.0.1:3030` | LLM/image sidecar; token required on non-loopback bind |

## Start / stop

```bash
docker compose up -d --build
docker compose logs -f backend worker
docker compose down
```

Compose fails fast unless `JWT_SECRET` and `AI_GATEWAY_TOKEN` are set.

## Health and readiness

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/version
curl -fsS http://127.0.0.1:8000/api/v1/metrics
```

`/metrics` exposes aggregate counters only: HTTP requests, job outcomes and
credit movements. It never includes user identifiers.

## Configuration checklist

```env
APP_ENV=production
JWT_SECRET=<64+ hex chars>
AI_GATEWAY_TOKEN=<strong shared token>
RATELIMIT_ENABLED=true
FILES_PUBLIC=false
CORS_ORIGINS=https://your-domain.example
MODERATION_API_URL=https://your-moderation-service.example/check
MODERATION_FAIL_CLOSED=true
STRIPE_SECRET_KEY=<your key>
STRIPE_WEBHOOK_SECRET=<your endpoint secret>
```

Never set `MODERATION_FAIL_CLOSED=false` unless an operator explicitly accepts
availability over safety.

## Job recovery

Jobs are leased, not dequeued destructively:

- A worker claims a `PENDING` row with a `worker_id` and `lease_until`.
- The worker heartbeats every `JOB_LEASE_SECONDS/3`.
- If a worker dies, another worker reclaims rows whose lease expired.
- `attempts` records claim count; investigate jobs with repeated attempts.

Useful SQL (read-only):

```sql
SELECT id, status, worker_id, lease_until, attempts
FROM generation_jobs
WHERE status IN ('pending', 'processing')
ORDER BY created_at;
```

## Credits and refunds

- Every charge/refund is an append-only `credit_ledger` row.
- Job charge uses `operation_key = job_charge:<job_id>`.
- Stripe top-ups use `stripe:<sha256(session_id)>`.
- Duplicate webhook deliveries cannot double-grant credits.

If a job fails after charging, the pipeline writes a compensating refund with a
unique operation key. Verify the ledger before re-running a failed job.

## Storage lifecycle

- Artifacts live under `jobs/<job_id>/…`.
- URLs are HMAC-signed and expire (`FILES_PUBLIC=false`).
- `STORAGE_TTL_DAYS` controls cleanup; default is 7 days.
- Back up the database and the storage volume together.

## Incident response

| Symptom | First actions |
| --- | --- |
| Jobs stuck `PROCESSING` | Check worker logs, lease timestamps and provider timeouts; restart worker after recording evidence |
| `moderation_unavailable` spike | Check moderator health; keep fail-closed; do not disable globally without approval |
| Stripe webhook failures | Verify raw-body signature, endpoint secret, timestamp skew and replay log |
| Provider 429/5xx | Reduce concurrency, verify key quota, rely on refund path for failed jobs |
| Credit mismatch | Query `credit_ledger` by `operation_key`; never edit rows directly |

## Rollout / rollback

1. Deploy from a tagged release with a published SBOM.
2. Watch error rate, job terminal status distribution and credit refund count.
3. Roll back by redeploying the previous image tag; database migrations are
   additive and backward-compatible by policy.
