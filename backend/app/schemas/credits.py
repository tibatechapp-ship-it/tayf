"""Credits schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    delta: int
    balance_after: int
    reason: str
    job_id: UUID | None
    created_at: datetime


class CreditsOut(BaseModel):
    balance: int
    entries: list[LedgerEntryOut]
