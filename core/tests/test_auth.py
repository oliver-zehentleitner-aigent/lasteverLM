from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from lasteverlm_core import (
    DEMO_USER_ID,
    JWT_ISSUER,
    AuthError,
    AuthSettings,
    ConfigError,
    current_user,
    issue_jwt,
    verify_jwt,
)

SECRET = "test-secret-with-enough-length-for-hs256"
DEMO = "demo-token-123"


def test_issue_and_verify_roundtrip() -> None:
    user = uuid4()
    now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
    token = issue_jwt(user, SECRET, now=now)
    claims = verify_jwt(token, SECRET)
    assert claims.sub == user
    assert claims.exp == now + timedelta(days=7)
    assert jwt.decode(token, SECRET, algorithms=["HS256"])["iss"] == JWT_ISSUER


def test_verify_rejects_wrong_secret_expired_and_foreign_issuer() -> None:
    user = uuid4()
    with pytest.raises(AuthError):
        verify_jwt(issue_jwt(user, SECRET), "other-secret-of-sufficient-length-1234")
    old = datetime.now(UTC) - timedelta(days=8)
    with pytest.raises(AuthError):
        verify_jwt(issue_jwt(user, SECRET, now=old), SECRET)
    foreign = jwt.encode(
        {"sub": str(user), "iss": "someone-else", "exp": datetime.now(UTC) + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verify_jwt(foreign, SECRET)


def test_verify_rejects_non_uuid_subject() -> None:
    token = jwt.encode(
        {"sub": "bob", "iss": JWT_ISSUER, "exp": datetime.now(UTC) + timedelta(hours=1)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verify_jwt(token, SECRET)


def test_current_user_jwt_then_demo_both_configured() -> None:
    auth = AuthSettings(jwt_secret=SECRET, demo_token=DEMO)
    user = uuid4()
    principal = current_user(f"Bearer {issue_jwt(user, SECRET)}", auth)
    assert (principal.user_id, principal.scheme) == (user, "jwt")
    principal = current_user(f"bearer {DEMO}", auth)
    assert (principal.user_id, principal.scheme) == (DEMO_USER_ID, "demo")
    with pytest.raises(AuthError):
        current_user("Bearer nonsense", auth)


def test_current_user_jwt_only_rejects_demo_token() -> None:
    auth = AuthSettings(jwt_secret=SECRET, demo_token=None)
    with pytest.raises(AuthError):
        current_user(f"Bearer {DEMO}", auth)


def test_current_user_demo_only_rejects_jwt() -> None:
    auth = AuthSettings(jwt_secret=None, demo_token=DEMO)
    assert current_user(f"Bearer {DEMO}", auth).user_id == DEMO_USER_ID
    with pytest.raises(AuthError):
        current_user(f"Bearer {issue_jwt(uuid4(), SECRET)}", auth)


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc", DEMO])
def test_current_user_rejects_malformed_header(header: str | None) -> None:
    with pytest.raises(AuthError):
        current_user(header, AuthSettings(jwt_secret=SECRET, demo_token=DEMO))


def test_demo_user_id_is_the_contract_value() -> None:
    assert str(DEMO_USER_ID) == "00000000-0000-4000-8000-000000000001"


def test_settings_from_env_require_one_scheme() -> None:
    assert AuthSettings.from_env({"DEMO_TOKEN": " x "}) == AuthSettings(None, "x")
    assert AuthSettings.from_env({"AUTH_JWT_SECRET": SECRET, "DEMO_TOKEN": ""}) == AuthSettings(
        SECRET, None
    )
    with pytest.raises(ConfigError):
        AuthSettings.from_env({})


def test_a_short_jwt_secret_is_refused_wherever_settings_are_built() -> None:
    with pytest.raises(ConfigError, match="AUTH_JWT_SECRET must be at least 32 bytes"):
        AuthSettings.from_env({"AUTH_JWT_SECRET": "s" * 31})
    with pytest.raises(ConfigError, match="at least 32 bytes"):
        AuthSettings(jwt_secret="short", demo_token=None)
    assert AuthSettings("s" * 32, None).jwt_secret == "s" * 32
