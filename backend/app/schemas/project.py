"""Request/response contracts for projects.

Input and output models are separate on purpose:
- ``ProjectCreate``/``ProjectUpdate`` forbid unknown fields, so a client cannot
  mass-assign ``id``, ``status`` or ``created_at``;
- ``ProjectRead`` is an allow-list — internal columns can never leak by accident.

Since the unified merge the owner is NEVER a body parameter: it comes from the
JWT (``deps.get_current_user``). ``ProjectRead.job_count`` is enriched by the
API layer, not stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ProjectStatus

NAME_MAX = 100
DESCRIPTION_MAX = 500

Name = Annotated[str, Field(min_length=1, max_length=NAME_MAX)]
Description = Annotated[str | None, Field(default=None, max_length=DESCRIPTION_MAX)]


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("name must not be blank")
    return cleaned


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class ProjectBase(BaseModel):
    name: Name
    description: Description = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("description")
    @classmethod
    def _description_normalized(cls, value: str | None) -> str | None:
        return _clean_description(value)


class ProjectCreate(ProjectBase):
    """Body of ``POST /projects`` — the owner is the authenticated user."""

    model_config = ConfigDict(extra="forbid")


class ProjectUpdate(BaseModel):
    """Body of ``PATCH /projects/{id}`` — every field optional (partial update)."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("description")
    @classmethod
    def _description_normalized(cls, value: str | None) -> str | None:
        return _clean_description(value)


class ProjectRead(ProjectBase):
    """Response model — exactly what a client is allowed to see."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    job_count: int = 0
