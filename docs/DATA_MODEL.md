# Data model — unified studio schema

Engine-agnostic by design: **SQLite in development, PostgreSQL in production**,
the same Alembic scripts on both (migration `a347dd0c8c67` → `c3d9e5f81a42`).

```
users ──1:N── projects ──1:N── generation_jobs
  │ id (UUID)      │ id (UUID)          │ id (UUID)
  │                └─ user_id FK CASCADE └─ project_id FK CASCADE
  └──1:N── credit_ledger (user_id FK CASCADE, job_id FK SET NULL)
```

## Tables

### `users`
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK, generated in Python (`uuid4`) |
| `email` | varchar(320) | UNIQUE, normalized to lowercase+trim in the repository |
| `username` | varchar(32) | UNIQUE, canonical **lowercase** `[a-z0-9_]{3,32}` (login identifier) |
| `hashed_password` | varchar(255) | Argon2id — never plaintext, never logged |
| `is_active` | boolean | NOT NULL, default true |
| `last_login_at` | timestamptz | set by `POST /auth/login` |
| `created_at`, `updated_at` | timestamptz | UTC, always timezone-aware (`UTCDateTime`) |

### `projects`
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, **ON DELETE CASCADE** |
| `name` | varchar(120) | NOT NULL, trimmed, 1–120 chars |
| `description` | text | NULL |
| `status` | varchar(24) | `draft \| active \| archived`, CHECK constraint |
| `created_at`, `updated_at` | timestamptz | UTC |

> **Wire contract:** the API exposes this column as `owner_id`
> (`Project.owner_id` is a read-only property over `user_id`).

Index: `ix_projects_user_id_created_at (user_id, created_at)` — the hot query
is "this user's projects, newest first", paginated (limit clamped to 100).

### `generation_jobs`
The durable record of the full pipeline; every pipeline step commits progress.

| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `project_id` | UUID | FK → `projects.id`, **ON DELETE CASCADE** |
| `prompt` | text | the user's request (safety-screened pre-insert) |
| `num_scenes` | integer | 2–8, cost = `num_scenes × CREDIT_PER_SCENE` |
| `aspect` | varchar(10) | `16:9 \| 9:16 \| 1:1` |
| `style` | varchar(40) | e.g. `cinematic`, `anime` |
| `input_params` | JSON | provider extras (audit trail) |
| `provider_name` | varchar(64) | `mock` \| `zai_gateway` \| `openai_compatible` \| `safety` |
| `model_version` | varchar(64) | exact model id used |
| `simulated` | boolean | **honesty flag**: true ONLY for the mock provider |
| `status` | varchar(24) | `pending \| processing \| completed \| failed \| rejected \| cancelled`, CHECK |
| `error_message` | text | set when a job fails (credits are refunded) |
| `rejection_reason` | text | set by the safety pre-filter (never charged) |
| `safety_category` | varchar(40) | `empty` \| `too_long` \| `blocked_term` \| `empty_artifact` |
| `storyboard` | JSON | `{title, scenes:[{index, description, image_prompt, duration_seconds, image_url}]}` |
| `result_url` | varchar(1024) | MP4 URL on completion (wire name: `output_url`) |
| `thumbnail_url` | varchar(1024) | JPEG thumbnail |
| `video_size_bytes` | integer | artifact size |
| `duration_seconds` | float | video duration |
| `credits_charged` | integer | net charge (0 after a full refund) |
| `completed_at` | timestamptz | NULL until terminal state |
| `created_at`, `updated_at` | timestamptz | UTC |

Index: `ix_generation_jobs_project_id_created_at (project_id, created_at)`.

### `credit_ledger` (append-only)
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, ON DELETE CASCADE, indexed |
| `job_id` | UUID | FK → `generation_jobs.id`, **ON DELETE SET NULL** — financial history survives job deletion |
| `delta` | integer | negative = charge, positive = grant/refund |
| `balance_after` | integer | running balance for fast audits |
| `reason` | varchar(60) | `signup_bonus` \| `job_charge` \| `refund_job_failed` |
| `created_at` | timestamptz | UTC |

Balance of a user = `SUM(delta)`. Rows are never updated or deleted.

## Lifecycle of a job

```
            safety pre-filter
pending ───────────────────────▶ rejected      (never charged)
   │ charge num_scenes × 1 (ledger)
   ▼
processing ── storyboard → keyframes → ffmpeg MP4
   │            every failure: failed + full refund
   ▼
completed      (result_url + thumbnail_url + storyboard JSON)
```

## Why these choices

| Choice | Reason |
|---|---|
| UUID PKs | safe to expose in URLs; no enumeration; portable (`sa.Uuid`) |
| VARCHAR + CHECK enums | readable rows; works identically on SQLite and PostgreSQL |
| `UTCDateTime` decorator | SQLite returns naive datetimes; this normalizes in/out so the wire contract never mixes offset styles |
| Deterministic constraint names | Alembic downgrades must find exactly the constraint they created |
| append-only ledger | money-like data must be auditable; corrections are new rows, never edits |
