"""Payment / top-up wire schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TopUpPackageOut(BaseModel):
    name: str
    credits: int
    price_cents: int
    currency: str


class TopUpPackagesOut(BaseModel):
    packages: list[TopUpPackageOut]
    configured: bool


class TopUpCheckoutIn(BaseModel):
    package: str = Field(min_length=1, max_length=32)


class CheckoutSessionOut(BaseModel):
    session_id: str
    checkout_url: str


class StripeWebhookOut(BaseModel):
    received: bool
    credited: bool = False
