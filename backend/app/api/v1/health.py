"""Health, version + metrics endpoints.

``/metrics`` exposes aggregate Prometheus counters (no user data, no
identifiers). Disable with ``METRICS_ENABLED=false`` — the route then 404s.
"""

import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.metrics import REGISTRY

# Single source of truth for the product version (FastAPI app + /version).
APP_VERSION = "0.5.0"

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


@router.get(
    "/metrics",
    summary="Prometheus counters (aggregate, no user data)",
    responses={404: {"description": "Metrics disabled via METRICS_ENABLED=false"}},
)
def metrics() -> Response:
    if not get_settings().METRICS_ENABLED:
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المقاييس معطّلة")
    return Response(
        content=REGISTRY.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
