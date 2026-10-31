"""Auth endpoints: register / login / me — REAL Argon2id + JWT, no fakes.

Registration grants the signup bonus atomically with the account creation:
a user can never exist with an empty ledger (audit invariant).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_session
from app.models import User
from app.repositories import user_repository
from app.schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut, UserOut
from app.services import credits

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(db: Session, user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=UserOut.model_validate(user),
        balance=credits.balance_of(db, user.id),
    )


@router.post(
    "/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED
)
def register(payload: RegisterIn, db: Session = Depends(get_session)) -> TokenOut:
    settings = get_settings()
    existing = user_repository.get_by_email(db, payload.email)
    if existing is None:
        existing = user_repository.get_by_username(db, payload.username)
    if existing is not None:
        if existing.email.lower() == payload.email.strip().lower():
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="البريد الإلكتروني مستخدم بالفعل"
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="اسم المستخدم مستخدم بالفعل"
        )

    try:
        user = user_repository.create_user(
            db,
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
        )
        credits.grant(db, user.id, settings.SIGNUP_CREDITS, reason="signup_bonus")
        db.commit()
    except IntegrityError as exc:  # race safety: two parallel registers
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="الحساب موجود بالفعل"
        ) from exc
    except ValueError as exc:  # repository validation guard
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.refresh(user)
    return _token_response(db, user)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_session)) -> TokenOut:
    user = user_repository.get_by_login(db, payload.username_or_email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="بيانات الدخول غير صحيحة"
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="الحساب معطّل")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return _token_response(db, user)


@router.get("/me", response_model=MeOut)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(current_user),
        balance=credits.balance_of(db, current_user.id),
    )
