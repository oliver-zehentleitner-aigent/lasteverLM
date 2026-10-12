"""API schemas, prefix ``/api/account``, as fixed in the family's ``docs/architecture.md`` v1."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .contracts import User

__all__ = ["User"]

# Shape only: one @, no whitespace, something on both sides. Deliverability is the
# mail server's call, and reserved names such as demo@localhost must stay valid here.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$"
    ),
]


class RequestLinkBody(BaseModel):
    email: Email


class LoginResponse(BaseModel):
    jwt: str
    user: User


class RedeemBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class VisitBody(BaseModel):
    path: str = Field(min_length=1, max_length=512)


# --- admin -------------------------------------------------------------------


class Smtp(BaseModel):
    """Read shape: the password is write-only and never returned."""

    host: str
    port: int
    username: str
    from_address: str
    starttls: bool


class SmtpUpdate(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    username: str = ""
    password: str | None = None  # omitted or null keeps the stored password
    from_address: Email
    starttls: bool = True


class DomainSettings(BaseModel):
    allowed_domains: list[str]


class AdminUser(BaseModel):
    id: uuid.UUID
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    balance_cents: int
    usage_cents: int


class AdminLogin(BaseModel):
    user_id: uuid.UUID
    email: str
    at: datetime


class AdminVisit(BaseModel):
    day: date
    path: str
    visits: int
    unique: int


class AdminBlock(BaseModel):
    ip: str
    blocked_until: datetime
    strikes: int
    updated_at: datetime


class AdminBan(BaseModel):
    ip: str
    reason: str
    created_at: datetime
    lifted_at: datetime | None


class AdminAccess(BaseModel):
    at: datetime
    ip: str
    method: str
    path: str
    status: int
    user_id: uuid.UUID | None
    service: str


class CreateVouchersBody(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)  # null uses the configured default
    count: int = Field(default=1, ge=1, le=100)


class CreateVouchersResponse(BaseModel):
    codes: list[str]  # shown exactly once; only their hashes are stored


class Health(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    error: str
