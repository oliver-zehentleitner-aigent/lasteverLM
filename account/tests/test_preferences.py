"""Per-user preferences: defaults, partial update, validation, the demo user."""

from __future__ import annotations

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import DEMO_TOKEN, FakeMailer, bearer, login

PREFS = "/api/account/me/preferences"
UNSET = {"ui_language": None, "output_language": None, "audio_voice": None}


def test_preferences_partial_update_and_clear(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "alice@example.org")
    h = bearer(token)
    assert client.get(PREFS, headers=h).json() == UNSET

    r = client.put(PREFS, json={"ui_language": "de", "audio_voice": "ryan"}, headers=h)
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.org"  # the full user comes back
    assert r.json()["preferences"] == {
        "ui_language": "de",
        "output_language": None,
        "audio_voice": "ryan",
    }

    # absent keys are kept, a null clears
    r = client.put(PREFS, json={"output_language": "en-US", "audio_voice": None}, headers=h)
    assert r.json()["preferences"] == {
        "ui_language": "de",
        "output_language": "en-US",
        "audio_voice": None,
    }
    assert client.get("/api/account/me", headers=h).json()["preferences"]["ui_language"] == "de"
    assert client.get(PREFS, headers=h).json()["output_language"] == "en-US"


def test_preferences_are_validated_by_shape(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "alice@example.org")
    h = bearer(token)
    for body in (
        {"ui_language": "fr"},
        {"output_language": "not a language"},
        {"audio_voice": "Alloy!"},
        {"audio_voice": "x" * 65},
    ):
        r = client.put(PREFS, json=body, headers=h)
        assert r.status_code == 422, body
    assert client.get(PREFS, headers=h).json() == UNSET


def test_stored_values_that_no_longer_validate_read_as_unset(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, user = login(client, mailer, "alice@example.org")
    import uuid

    uid = uuid.UUID(user["id"])
    repo.users[uid] = UserRecord(
        uid,
        "alice@example.org",
        True,
        repo.users[uid].created_at,
        None,
        {"ui_language": "klingon", "audio_voice": "ryan", "legacy_key": 1},
    )
    assert client.get(PREFS, headers=bearer(token)).json() == {
        "ui_language": None,
        "output_language": None,
        "audio_voice": "ryan",
    }


def test_demo_user_cannot_change_preferences(client: TestClient, repo: MemoryRepository) -> None:
    from datetime import UTC, datetime

    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, "demo@localhost", False, datetime.now(UTC), None
    )
    h = bearer(DEMO_TOKEN)
    assert client.get(PREFS, headers=h).json() == UNSET
    r = client.put(PREFS, json={"ui_language": "de"}, headers=h)
    assert r.status_code == 403
    assert client.get(PREFS, headers=h).json() == UNSET
