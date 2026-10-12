from uuid import uuid4

import jwt
import pytest

from lasteverlm_ingest.contracts import DEMO_USER_ID, AuthError, verify_token

KEY = "k" * 32
OTHER = "o" * 32


def test_demo_token_maps_to_demo_user():
    assert verify_token("secret", jwt_secret=None, demo_token="secret") == DEMO_USER_ID


def test_wrong_demo_token():
    with pytest.raises(AuthError):
        verify_token("nope", jwt_secret=None, demo_token="secret")


def make_jwt(user, key=KEY, **extra):
    return jwt.encode({"sub": str(user), "iss": "lasteverlm", **extra}, key, algorithm="HS256")


def test_jwt_subject_is_the_user():
    user = uuid4()
    assert verify_token(make_jwt(user), jwt_secret=KEY, demo_token=None) == user


def test_jwt_bad_signature_issuer_or_subject():
    with pytest.raises(AuthError):
        verify_token(make_jwt(uuid4(), key=OTHER), jwt_secret=KEY, demo_token=None)
    with pytest.raises(AuthError):
        verify_token(jwt.encode({"sub": str(uuid4())}, KEY), jwt_secret=KEY, demo_token=None)
    with pytest.raises(AuthError):
        verify_token(make_jwt(uuid4(), iss="other"), jwt_secret=KEY, demo_token=None)
    with pytest.raises(AuthError):
        verify_token(jwt.encode({"iss": "lasteverlm"}, KEY), jwt_secret=KEY, demo_token=None)
    with pytest.raises(AuthError):
        verify_token(make_jwt("not-a-uuid"), jwt_secret=KEY, demo_token=None)


def test_both_schemes_configured_at_once():
    user = uuid4()
    assert verify_token(make_jwt(user), jwt_secret=KEY, demo_token="secret") == user
    assert verify_token("secret", jwt_secret=KEY, demo_token="secret") == DEMO_USER_ID
    with pytest.raises(AuthError, match="invalid token"):
        verify_token("neither", jwt_secret=KEY, demo_token="secret")


def test_no_scheme_at_all():
    with pytest.raises(AuthError, match="no authentication scheme"):
        verify_token("x", jwt_secret=None, demo_token=None)
