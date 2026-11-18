"""Credit top-ups and Stripe webhook fulfillment."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.stripe_webhooks import (
    StripeSignatureError,
    operation_key_for_session,
    verify_stripe_event,
)
from app.db.session import get_session
from app.models import User
from app.schemas.payments import (
    CheckoutSessionOut,
    StripeWebhookOut,
    TopUpCheckoutIn,
    TopUpPackageOut,
    TopUpPackagesOut,
)
from app.services import credits, payments

router = APIRouter(tags=["payments"])

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

FULFILLED_EVENTS = frozenset({"checkout.session.completed", "checkout.session.async_payment_succeeded"})


@router.get("/payments/topup/packages", response_model=TopUpPackagesOut)
def list_topup_packages() -> TopUpPackagesOut:
    settings = get_settings()
    return TopUpPackagesOut(
        packages=[
            TopUpPackageOut(
                name=package.name,
                credits=package.credits,
                price_cents=package.price_cents,
                currency=package.currency,
            )
            for package in settings.topup_packages
        ],
        configured=settings.stripe_checkout_configured,
    )


@router.post(
    "/payments/topup/checkout-session",
    response_model=CheckoutSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Stripe Checkout Session for a fixed credit package",
    responses={400: {"description": "Unknown package"}, 503: {"description": "Payments not configured"}},
)
async def create_topup_checkout(
    payload: TopUpCheckoutIn,
    current_user: CurrentUser,
) -> CheckoutSessionOut:
    settings = get_settings()
    if not settings.stripe_checkout_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "الدفع غير مفعّل بعد")
    package = settings.get_topup_package(payload.package)
    if package is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "حزمة الرصيد غير موجودة")
    try:
        session = await payments.create_checkout_session(settings, user_id=current_user.id, package=package)
    except payments.StripeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return CheckoutSessionOut(session_id=session.id, checkout_url=session.url)


def _payload_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@router.post(
    "/webhooks/stripe",
    response_model=StripeWebhookOut,
    include_in_schema=False,
    summary="Stripe webhook: grant credits only for verified paid checkouts",
)
async def stripe_webhook(request: Request, db_session: SessionDep) -> StripeWebhookOut:
    settings = get_settings()
    if not settings.stripe_webhook_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook secret is not configured")

    raw_body = await request.body()
    try:
        event = verify_stripe_event(raw_body, request.headers.get("stripe-signature"), settings.STRIPE_WEBHOOK_SECRET)
    except StripeSignatureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe signature") from exc

    event_type = event.get("type")
    if event_type not in FULFILLED_EVENTS:
        return StripeWebhookOut(received=True)

    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe event body")
    if obj.get("payment_status") != "paid":
        # Delayed payment methods fire `async_payment_succeeded` later.
        return StripeWebhookOut(received=True)

    session_id = obj.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing checkout session id")
    metadata = obj.get("metadata")
    if not isinstance(metadata, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing checkout metadata")

    package = settings.get_topup_package(str(metadata.get("package", "")))
    credited_amount = _payload_int(metadata.get("credits"))
    amount_total = _payload_int(obj.get("amount_total"))
    if (
        package is None
        or credited_amount != package.credits
        or amount_total != package.price_cents
        or obj.get("currency") != package.currency
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Checkout does not match a configured package")

    try:
        user_id = uuid.UUID(str(obj.get("client_reference_id", "")))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid user reference") from exc
    if db_session.get(User, user_id) is None:
        # Deleted accounts cannot receive credits; acknowledge so Stripe stops retrying.
        return StripeWebhookOut(received=True)

    operation_key = operation_key_for_session(session_id)
    credits.grant(
        db_session,
        user_id,
        package.credits,
        reason="topup_stripe",
        operation_key=operation_key,
    )
    db_session.commit()
    return StripeWebhookOut(received=True, credited=True)
