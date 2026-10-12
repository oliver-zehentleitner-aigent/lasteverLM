"""Local mirror of the parts of ``lasteverLM-core`` this service needs.

``lasteverLM-core`` (shared pydantic models, settings, JWT issue/verify helpers,
the demo-token path) is being written in parallel. Until it is published, the
pieces are mirrored here so this service can be built and tested. Once core is
available this module becomes a thin re-export, see ``context/auth.md``.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "lasteverlm"

# The user id every caller of the shared demo token resolves to. Shared with the
# ingest and rag services; it is part of the API contract.
DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER_EMAIL = "demo@localhost"


class AuthError(Exception):
    """The request carries no valid credential."""


class User(BaseModel):
    """The account view every service and the frontend share."""

    id: uuid.UUID
    email: str
    is_admin: bool
    balance_cents: int
    created_at: datetime


class TokenClaims(BaseModel):
    sub: uuid.UUID
    exp: datetime


def issue_jwt(user_id: uuid.UUID, secret: str, ttl: timedelta, now: datetime | None = None) -> str:
    """Issue an HS256 session token. ``sub`` is the user id."""
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str, secret: str) -> TokenClaims:
    """Return the claims of a valid session token, or raise AuthError."""
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER)
    except jwt.PyJWTError as exc:
        raise AuthError("invalid session token") from exc
    try:
        return TokenClaims(
            sub=uuid.UUID(str(payload["sub"])),
            exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        raise AuthError("malformed session token") from exc


def resolve_bearer(token: str, secret: str, demo_token: str | None) -> uuid.UUID:
    """Map a bearer token to a user id: a session JWT first, the demo token second."""
    if not token:
        raise AuthError("missing bearer token")
    try:
        return verify_jwt(token, secret).sub
    except AuthError:
        if demo_token and hmac.compare_digest(token, demo_token):
            return DEMO_USER_ID
        raise
