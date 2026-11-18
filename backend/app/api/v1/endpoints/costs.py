"""Cost dashboard endpoint — owner-scoped credits and per-stage timings."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import User
from app.schemas.costs import CostReportOut
from app.services import cost_report

router = APIRouter(prefix="/costs", tags=["costs"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=CostReportOut, summary="My generation costs and stage timings")
def my_costs(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CostReportOut:
    return CostReportOut.model_validate(
        cost_report.build_report(session, current_user.id, limit)
    )
