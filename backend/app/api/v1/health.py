"""Health + version endpoints — the contract the frontend uses to prove connectivity."""

import sys
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

# Single source of truth for the product version (FastAPI app + /version).
APP_VERSION = "0.4.0"

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, summary="Service health")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        environment=settings.APP_ENV,
        timestamp=datetime.now(timezone.utc),
    )


class VersionResponse(BaseModel):
    service: str
    version: str
    api_prefix: str
    environment: str
    python_version: str
    storage_backend: str
    ai_provider: str
    timestamp: datetime


@router.get("/version", response_model=VersionResponse, summary="Build & runtime info")
def version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        service=settings.APP_NAME,
        version=APP_VERSION,
        api_prefix=settings.API_V1_PREFIX,
        environment=settings.APP_ENV,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        storage_backend=settings.STORAGE_BACKEND,
        ai_provider=settings.AI_PROVIDER,
        timestamp=datetime.now(timezone.utc),
    )
