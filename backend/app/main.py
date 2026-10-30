"""Tayf API — entry point.

Stage 1 (running skeleton): only the health contract exists on purpose.
Database, auth and generation endpoints arrive in later stages and must not be
faked here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Tayf API",
    version="0.1.0",
    description="AI video generation platform — stage 1 skeleton.",
)

# The Vite dev server proxies /api, so CORS is only needed for direct calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # no cookie-based auth exists yet
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
