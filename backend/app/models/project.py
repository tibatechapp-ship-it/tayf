"""Project model — a user's container for generation jobs."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProjectStatus

if TYPE_CHECKING:  # avoid import cycles at runtime
    from app.models.generation_job import GenerationJob
    from app.models.user import User


def enum_column(enum_cls: type, name: str, length: int = 24) -> Enum:
    """VARCHAR + CHECK instead of a native DB enum — portable across engines."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,  # real CHECK constraint on every engine
        length=length,
        validate_strings=True,
        values_callable=lambda members: [m.value for m in members],
    )


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        # Serves the only hot query: a user's projects, newest first.
        Index("ix_projects_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus, "project_status"),
        default=ProjectStatus.DRAFT,
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="projects")
    jobs: Mapped[list["GenerationJob"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Project {self.id} {self.name!r}>"
