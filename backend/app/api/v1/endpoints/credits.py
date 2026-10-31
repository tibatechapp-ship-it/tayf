"""Credits endpoints — read the authenticated user's balance + ledger."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models import CreditLedger, User
from app.schemas.credits import CreditsOut
from app.services import credits

router = APIRouter(prefix="/credits", tags=["credits"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=CreditsOut, summary="My balance + recent ledger")
def my_credits(
    current_user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CreditsOut:
    entries = session.execute(
        select(CreditLedger)
        .where(CreditLedger.user_id == current_user.id)
        .order_by(CreditLedger.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return CreditsOut(
        balance=credits.balance_of(session, current_user.id),
        entries=list(entries),
    )
