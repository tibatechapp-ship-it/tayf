"""Domain enums stored as VARCHAR + CHECK (portable, readable, no native enum)."""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class GenerationStatus(StrEnum):
    """Stage-2 lifecycle.

    Stage 8 extends this with the provider-facing states
    (queued/validating/submitted/cancelled) — a migration, not a rewrite.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
