"""Bearer-token resolution: one function, two schemes.

Every request carries `Authorization: Bearer <token>`. The token is either
a session JWT the account service issued after a magic link (HS256,
`sub` = user id, issuer `lasteverlm`, 7 days) or the shared demo token
from `DEMO_TOKEN`, which resolves to the fixed demo user. Both schemes
may be configured at once; a deployment without `DEMO_TOKEN` accepts only
JWTs, production unsets it. `AuthSettings.from_env` refuses a deployment
that configures neither.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt
from pydantic import BaseModel

from .models import DEMO_USER_ID
from .settings import ConfigError, env_optional

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "lasteverlm"
JWT_TTL = timedelta(days=7)

AuthScheme = Literal["jwt", "demo"]


class AuthError(Exception):
    """The request carries no valid credential. Services answer 401."""


class TokenClaims(BaseModel):
    sub: UUID
    exp: datetime


@dataclass(frozen=True)
class Principal:
    """Who a request acts as, and through which scheme it was recognised."""

    user_id: UUID
    scheme: AuthScheme


@dataclass(frozen=True)
class AuthSettings:
    """`AUTH_JWT_SECRET` and `DEMO_TOKEN`; at least one is required."""

    jwt_secret: str | None
    demo_token: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AuthSettings:
        settings = cls(
            jwt_secret=env_optional("AUTH_JWT_SECRET", env),
            demo_token=env_optional("DEMO_TOKEN", env),
        )
        if settings.jwt_secret is None and settings.demo_token is None:
            raise ConfigError("AUTH_JWT_SECRET or DEMO_TOKEN is required; neither is set")
        return settings


def issue_jwt(
    user_id: UUID, secret: str, ttl: timedelta = JWT_TTL, now: datetime | None = None
) -> str:
    """Issue a session token. `sub` is the user id; the account service calls this."""
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str, secret: str) -> TokenClaims:
    """The claims of a valid session token, or `AuthError`."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid session token") from exc
    try:
        return TokenClaims(
            sub=UUID(str(payload["sub"])),
            exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError("malformed session token") from exc


def bearer_token(authorization: str | None) -> str:
    """The token of an `Authorization: Bearer <token>` header, or `AuthError`."""
    if authorization is None:
        raise AuthError("missing bearer token")
    scheme, _, token = authorization.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise AuthError("missing bearer token")
    return token


def current_user(authorization: str | None, auth: AuthSettings) -> Principal:
    """Resolve the `Authorization` header to a principal, or raise `AuthError`.

    A JWT is tried first when a secret is configured, the demo token
    second when one is configured (constant-time comparison). The two
    schemes are independent: a deployment with both accepts both.
    """
    token = bearer_token(authorization)
    if auth.jwt_secret is not None:
        try:
            return Principal(verify_jwt(token, auth.jwt_secret).sub, "jwt")
        except AuthError:
            if auth.demo_token is None:
                raise
    if auth.demo_token is not None and hmac.compare_digest(
        token.encode(), auth.demo_token.encode()
    ):
        return Principal(DEMO_USER_ID, "demo")
    raise AuthError("invalid bearer token")
