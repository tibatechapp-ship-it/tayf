"""Tayf Studio API — entry point.

The unified build (Stage 4 merge) provides, all REAL:
  - Auth: Argon2id + JWT (register / login / me)
  - Projects: repository-driven CRUD with ownership isolation
  - Jobs: safety screen -> credits -> background pipeline
          (storyboard -> keyframes -> ffmpeg MP4 -> storage)
  - Credits: append-only ledger, signup bonus, refunds on failure
  - Storage: local filesystem or any S3-compatible store, TTL cleanup
  - Safety: pre/post generation screening

Nothing here is faked. Providers that simulate output are flagged
`simulated=true` end to end (mock provider only).
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import (
    auth_router,
    credits_router,
    files_router,
    jobs_router,
    projects_router,
)
from app.api.v1.health import APP_VERSION, router as health_router
from app.core.config import get_settings
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.services.storage.factory import run_cleanup_once

settings = get_settings()


async def _cleanup_loop() -> None:
    """Periodically delete stored artifacts older than STORAGE_TTL_DAYS."""
    interval_seconds = max(settings.CLEANUP_INTERVAL_MINUTES, 1) * 60
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            deleted = await asyncio.to_thread(run_cleanup_once)
            if deleted:
                print(f"[cleanup] removed {deleted} expired artifact(s)")
        except Exception as exc:  # pragma: no cover - cleanup must never kill the app
            print(f"[cleanup] error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_loop())
    app.state.cleanup_task = cleanup_task
    yield
    cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup_task


app = FastAPI(
    title="Tayf Studio API",
    version=APP_VERSION,
    description=(
        "AI video generation platform (Arabic-first). The unified build adds "
        "real auth, credits, storage, safety and the full generation pipeline "
        "(SQLite in dev, PostgreSQL via DATABASE_URL).\n\n"
        "Providers: `mock` (clearly simulated) | `zai_gateway` (real, via the "
        "ai-gateway sidecar) | `openai_compatible` (real, bring your own key)."
    ),
    lifespan=lifespan,
)

# The Vite dev server proxies /api, so CORS is only needed for direct calls.
# Auth uses Authorization headers (no cookies), so credentials stay disabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Hardening + observability: applied last -> outermost (every response covered,
# including /docs and /api/v1/files/*).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(projects_router, prefix=settings.API_V1_PREFIX)
app.include_router(jobs_router, prefix=settings.API_V1_PREFIX)
app.include_router(credits_router, prefix=settings.API_V1_PREFIX)
app.include_router(files_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root() -> dict:
    return {
        "service": "tayf-studio",
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
    }
