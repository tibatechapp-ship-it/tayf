"""Generation job model — one text-to-video production run.

The durable record of the full pipeline:
prompt -> safety -> storyboard -> keyframes -> MP4 composition -> storage.

A job's state must survive a worker restart, so every pipeline step commits
its progress here. `simulated` is the honesty flag: True ONLY when the
provider fabricated the content locally (mock provider).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.enums import GenerationStatus
from app.models.project import enum_column

if TYPE_CHECKING:
    from app.models.credit_ledger import CreditLedger
    from app.models.project import Project


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        Index("ix_generation_jobs_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # --- the request ---
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    num_scenes: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    aspect: Mapped[str] = mapped_column(String(10), default="16:9", nullable=False)
    style: Mapped[str] = mapped_column(String(40), default="cinematic", nullable=False)
    input_params: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    # --- provider bookkeeping ---
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- lifecycle / safety ---
    status: Mapped[GenerationStatus] = mapped_column(
        enum_column(GenerationStatus, "generation_status"),
        default=GenerationStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_category: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # --- results ---
    storyboard: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    video_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="jobs")
    credit_entries: Mapped[list["CreditLedger"]] = relationship(  # noqa: F821
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GenerationJob {self.id} {self.status}>"
