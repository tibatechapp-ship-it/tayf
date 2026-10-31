"""Tayf API — entry point.

Stage 1: health contract. Stage 3: project CRUD (owner passed explicitly until
the Stage 4 authentication layer exists). Nothing here is faked.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import projects_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Tayf API",
    version="0.3.0",
    description=(
        "AI video generation platform. Stage 3 adds the project CRUD API "
        "(SQLite in dev, PostgreSQL via DATABASE_URL).\n\n"
        "**Auth pending:** endpoints take `owner_id` explicitly until Stage 4."
    ),
)

# The Vite dev server proxies /api, so CORS is only needed for direct calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # no cookie-based auth exists yet
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(projects_router, prefix=settings.api_v1_prefix)
