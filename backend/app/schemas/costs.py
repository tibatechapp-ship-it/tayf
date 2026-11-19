"""Cost dashboard wire schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class StageCostOut(BaseModel):
    stage: str
    events: int
    duration_ms: int
    credits: int


class ModelUsageOut(BaseModel):
    provider: str
    model_version: str
    simulated: bool
    jobs: int
    events: int
    duration_ms: int
    credits: int


class JobCostOut(BaseModel):
    job_id: UUID
    created_at: datetime | None = None
    status: str
    scenes: int
    credits_charged: int
    attributed_credits: int
    duration_ms: int
    model_version: str
    simulated: bool


class CostReportOut(BaseModel):
    balance: int
    credits_charged: int
    credits_refunded: int
    credits_net: int
    jobs_analyzed: int
    scenes_generated: int
    total_duration_ms: int
    attribution: str
    stages: list[StageCostOut]
    models: list[ModelUsageOut]
    recent_jobs: list[JobCostOut]
