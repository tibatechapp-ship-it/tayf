"""Generation job model — one request to one provider model.

Stage 7/8 fill this in (provider adapter, worker, WebSocket). The columns here
are the durable part: a job's state must survive a worker restart.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GenerationStatus
from app.models.project import enum_column

if TYPE_CHECKING:
    from app.models.project import Project


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        Index("ix_generation_jobs_project_id_created_at", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_params: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    status: Mapped[GenerationStatus] = mapped_column(
        enum_column(GenerationStatus, "generation_status"),
        default=GenerationStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="jobs")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GenerationJob {self.id} {self.status}>"
