"""Auth schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,32}$"


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(pattern=_USERNAME_PATTERN, min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    balance: int


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class MeOut(BaseModel):
    user: UserOut
    balance: int
