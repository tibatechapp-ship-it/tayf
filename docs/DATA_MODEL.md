# Data model — Stage 2

Engine-agnostic by design: **SQLite in development, PostgreSQL in production**,
the same Alembic scripts on both.

```
users ──1:N── projects ──1:N── generation_jobs
  id (UUID)      id (UUID)          id (UUID)
  email (UQ)     user_id (FK CASCADE) project_id (FK CASCADE)
```

## Tables

### `users`
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK, generated in Python (`uuid4`) |
| `email` | varchar(320) | UNIQUE, normalized to lowercase+trim in the repository |
| `hashed_password` | varchar(255) | never plaintext; hashing itself is Stage 5 (Argon2id) |
| `is_active` | boolean | NOT NULL, default true |
| `last_login_at` | timestamptz | NULL until the first successful login |
| `created_at`, `updated_at` | timestamptz | UTC, `updated_at` maintained by the ORM |

### `projects`
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, **ON DELETE CASCADE** |
| `name` | varchar(120) | NOT NULL, trimmed, 1–120 chars (repository validates; the API schema is stricter: 100) |
| `description` | text | NULL |
| `status` | varchar(24) | `draft \| active \| archived`, CHECK constraint |
| `created_at`, `updated_at` | timestamptz | UTC, always timezone-aware (`UTCDateTime` decorator) |

> **Wire contract:** the API exposes this column as `owner_id`
> (`Project.owner_id` is a read-only property over `user_id`). The database is not
> renamed — `user_id` stays the FK name; only the JSON contract uses `owner_id`.

Index: `ix_projects_user_id_created_at (user_id, created_at)` — the only hot
query is "this user's projects, newest first", and it is paginated (limit
clamped to 100 server-side).

### `generation_jobs`
| Column | Type | Rules |
|---|---|---|
| `id` | UUID | PK |
| `project_id` | UUID | FK → `projects.id`, **ON DELETE CASCADE** |
| `provider_name` | varchar(64) | e.g. `mock-dev` today, a real vendor in Stage 7 |
| `model_version` | varchar(64) | the exact model id the job was submitted with |
| `input_params` | JSON | prompt, duration, aspect ratio… (validated in Stage 4/7) |
| `status` | varchar(24) | `pending \| processing \| completed \| failed`, CHECK |
| `error_message` | text | set when a job fails |
| `result_url` | varchar(1024) | set when a job completes |
| `completed_at` | timestamptz | NULL until terminal state |
| `created_at`, `updated_at` | timestamptz | UTC |

Index: `ix_generation_jobs_project_id_created_at (project_id, created_at)`.

## Why these choices

| Choice | Reason |
|---|---|
| **UUID primary keys** | jobs/machines can mint ids without a central sequence; no id enumeration; merging data later doesn't collide. Cost: 32-char keys, acceptable at this scale. |
| **`sa.Uuid()`** | one column type → CHAR(32) on SQLite, native `uuid` on Postgres. Not a string column, not an int. |
| **Portable enum** (`native_enum=False`, `create_constraint=True`) | stores readable values in VARCHAR with a CHECK on both engines. A native Postgres enum would need a migration dance to add a state later. |
| **`sa.JSON()`** | provider payloads differ per vendor; JSONB-compatible on Postgres, TEXT-backed JSON with the JSON1 functions on SQLite. |
| **ON DELETE CASCADE + `PRAGMA foreign_keys=ON`** | deleting an account must not orphan projects/jobs. SQLite needs the pragma — it is set on every connection in `app/db/session.py`, and a test proves the DB (not the ORM) cascades. |
| **Filtered ownership lookups** | `get_project_by_id_and_owner()` returns `None` for "missing" *and* "not yours", so the API can answer 404 without leaking existence. |
| **`last_login_at`** | requested `update_last_login()` needs a column to write to. |
| **Stage-2 status set is 4 states** | Stage 8 adds `queued/validating/submitted/cancelled` as a migration, not a rewrite. |

## Migration files

`backend/migrations/versions/a347dd0c8c67_initial_schema.py`

Verified on this device:
- `alembic upgrade head` on an empty SQLite file → 3 tables + 2 indexes,
  CHECK constraints and `ON DELETE CASCADE` present in the emitted DDL;
- `alembic downgrade base` → only `alembic_version` remains;
- `upgrade head` again → clean, empty tables;
- `compare_metadata()` against the models → **no diff** (models and migrations
  cannot drift silently; this runs in the test suite).
