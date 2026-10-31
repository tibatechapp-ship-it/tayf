"""HTTP endpoint modules."""

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.credits import router as credits_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.jobs import router as jobs_router
from app.api.v1.endpoints.projects import router as projects_router

__all__ = [
    "auth_router",
    "credits_router",
    "files_router",
    "jobs_router",
    "projects_router",
]
