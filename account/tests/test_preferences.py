"""Per-user preferences: defaults, partial update, validation, the demo user."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import DEMO_TOKEN, FakeMailer, bearer, login

PREFS = "/api/account/me/preferences"
UNSET = {
    "ui_language": None,
    "output_language": None,
    "audio_voice": None,
    "trash_days": None,
    "pdf_capture": None,
    "theme": None,
    "tour_done": False,
    "verification_level": "basic",
}


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
        "trash_days": None,
        "pdf_capture": None,
        "theme": None,
        "tour_done": False,
        "verification_level": "basic",
    }

    # absent keys are kept, a null clears
    r = client.put(
        PREFS,
        json={
            "output_language": "en-US",
            "audio_voice": None,
            "trash_days": 30,
            "pdf_capture": "vision",
            "theme": "dark",
        },
        headers=h,
    )
    assert r.json()["preferences"] == {
        "ui_language": "de",
        "output_language": "en-US",
        "audio_voice": None,
        "trash_days": 30,
        "pdf_capture": "vision",
        "theme": "dark",
        "tour_done": False,
        "verification_level": "basic",
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
        {"trash_days": 0},
        {"trash_days": 366},
        {"trash_days": "soon"},
        {"pdf_capture": "ocr"},
        {"theme": "sepia"},
    ):
        r = client.put(PREFS, json=body, headers=h)
        assert r.status_code == 422, body
    assert client.get(PREFS, headers=h).json() == UNSET


def test_stored_values_that_no_longer_validate_read_as_unset(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, user = login(client, mailer, "alice@example.org")
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
        "trash_days": None,
        "pdf_capture": None,
        "theme": None,
        "tour_done": False,
        "verification_level": "basic",
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


def test_language_code_length_is_capped(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "alice@example.org")
    long_but_shaped = "de" + "-abcdefgh" * 5  # 47 chars, every subtag well-formed
    r = client.put(PREFS, json={"output_language": long_but_shaped}, headers=bearer(token))
    assert r.status_code == 422


def test_tour_done_is_false_until_set_and_null_resets_it(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, _ = login(client, mailer, "tourist@example.org")
    h = bearer(token)
    assert client.get(PREFS, headers=h).json()["tour_done"] is False
    r = client.put(PREFS, json={"tour_done": True}, headers=h)
    assert r.status_code == 200 and r.json()["preferences"]["tour_done"] is True
    client.put(PREFS, json={"theme": "light"}, headers=h)  # other keys keep it
    assert client.get(PREFS, headers=h).json()["tour_done"] is True
    client.put(PREFS, json={"tour_done": None}, headers=h)
    assert client.get(PREFS, headers=h).json()["tour_done"] is False
    assert client.put(PREFS, json={"tour_done": "yes"}, headers=h).status_code == 422


def test_verification_level_is_basic_until_set_and_null_resets_it(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, _ = login(client, mailer, "judge@example.org")
    h = bearer(token)
    assert client.get(PREFS, headers=h).json()["verification_level"] == "basic"
    for level in ("standard", "thorough", "bulletproof", "basic"):
        r = client.put(PREFS, json={"verification_level": level}, headers=h)
        assert r.status_code == 200 and r.json()["preferences"]["verification_level"] == level
    client.put(PREFS, json={"verification_level": "thorough"}, headers=h)
    client.put(PREFS, json={"theme": "dark"}, headers=h)  # other keys keep it
    me = client.get("/api/account/me", headers=h).json()["preferences"]
    assert me["verification_level"] == "thorough" and "judge_default" not in me
    client.put(PREFS, json={"verification_level": None}, headers=h)
    assert client.get(PREFS, headers=h).json()["verification_level"] == "basic"
    for bad in ("high", "", True, 2):
        r = client.put(PREFS, json={"verification_level": bad}, headers=h)
        assert r.status_code == 422, bad


@pytest.mark.parametrize(
    ("old", "level"),
    [("off", "basic"), ("low", "standard"), ("medium", "thorough"), ("high", "bulletproof")],
)
def test_an_old_client_s_judge_default_is_mapped(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, old: str, level: str
) -> None:
    token, user = login(client, mailer, "old-web@example.org")
    h = bearer(token)
    r = client.put(PREFS, json={"judge_default": old}, headers=h)
    assert r.status_code == 200 and r.json()["preferences"]["verification_level"] == level
    stored = repo.users[uuid.UUID(str(user["id"]))].preferences
    assert stored.get("verification_level", "basic") == level and "judge_default" not in stored


def test_judge_default_edge_cases(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, user = login(client, mailer, "edge@example.org")
    h = bearer(token)
    # both sent: the new field wins
    r = client.put(
        PREFS, json={"judge_default": "high", "verification_level": "standard"}, headers=h
    )
    assert r.json()["preferences"]["verification_level"] == "standard"
    # null resets, an unknown old value is a 422
    client.put(PREFS, json={"judge_default": None}, headers=h)
    assert client.get(PREFS, headers=h).json()["verification_level"] == "basic"
    assert client.put(PREFS, json={"judge_default": "max"}, headers=h).status_code == 422
    # a stored judge_default from before migration 0011 reads mapped
    uid = uuid.UUID(str(user["id"]))
    repo.users[uid] = replace(repo.users[uid], preferences={"judge_default": "medium"})
    assert client.get(PREFS, headers=h).json()["verification_level"] == "thorough"
