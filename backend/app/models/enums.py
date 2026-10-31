"""Domain enums stored as VARCHAR + CHECK (portable, readable, no native enum)."""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class GenerationStatus(StrEnum):
    """Full job lifecycle.

    pending -> processing -> completed
                    |-> failed          (provider/compose error, credits refunded)
    pending -> rejected                 (safety, never charged)
    pending/processing -> cancelled     (user action, credits refunded; Stage 6)
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> frozenset["GenerationStatus"]:
        return frozenset({cls.COMPLETED, cls.FAILED, cls.REJECTED, cls.CANCELLED})
