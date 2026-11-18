"""Auth endpoints: register / login / refresh / logout / me.

Registration grants the signup bonus atomically with the account creation:
a user can never exist with an empty ledger (audit invariant).

Session model: the access JWT is returned in the body (short-lived, kept in
browser memory); the refresh JWT is set ONLY as an HttpOnly, SameSite=Strict
cookie and is tracked server-side so rotation, reuse detection and logout are
real revocations instead of stateless theatre.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings, settings
from app.core.ratelimit import auth_rate_limit
from app.core.security import create_access_token, decode_refresh_token, hash_password, verify_password
from app.db.session import get_session
from app.models import User
from app.repositories import user_repository
from app.schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut, UserOut
from app.services import credits, refresh_tokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "tayf_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        max_age=settings.JWT_REFRESH_EXPIRES_DAYS * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.APP_ENV == "production",
        samesite="strict",
    )


def _token_response(db: Session, user: User, response: Response) -> TokenOut:
    raw_refresh = refresh_tokens.issue(db, user)
    _set_refresh_cookie(response, raw_refresh)
    return TokenOut(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=UserOut.model_validate(user),
        balance=credits.balance_of(db, user.id),
    )


def _invalid_refresh() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="رمز التحديث غير صالح أو منتهٍ"
    )


@router.post(
    "/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED
)
def register(
    payload: RegisterIn,
    response: Response,
    db: Session = Depends(get_session),
    _rl: None = Depends(auth_rate_limit),
) -> TokenOut:
    settings_now = get_settings()
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
        credits.grant(
            db,
            user.id,
            settings_now.SIGNUP_CREDITS,
            reason="signup_bonus",
            operation_key=f"signup:{user.id}",
        )
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
    return _token_response(db, user, response)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    response: Response,
    db: Session = Depends(get_session),
    _rl: None = Depends(auth_rate_limit),
) -> TokenOut:
    user = user_repository.get_by_login(db, payload.username_or_email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="بيانات الدخول غير صحيحة"
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="الحساب معطّل")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return _token_response(db, user, response)


@router.post("/refresh", response_model=TokenOut, summary="Rotate access + refresh cookies")
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    _rl: None = Depends(auth_rate_limit),
) -> TokenOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise _invalid_refresh()
    user_id = decode_refresh_token(raw)
    if user_id is None:
        raise _invalid_refresh()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _invalid_refresh()
    # Atomic single-use consumption: a replay revokes the whole family.
    if not refresh_tokens.consume(db, raw, user.id):
        raise _invalid_refresh()
    return _token_response(db, user, response)


@router.post("/logout", summary="Revoke the current refresh session")
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, str]:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        owner = decode_refresh_token(raw)
        if owner == current_user.id:
            refresh_tokens.revoke(db, raw, current_user.id)
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return {"status": "ok"}


@router.get("/me", response_model=MeOut)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(current_user),
        balance=credits.balance_of(db, current_user.id),
    )
