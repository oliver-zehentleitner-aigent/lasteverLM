"""The public price list: end prices from measured costs through today's rules, no login."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from lasteverlm_core import PRICING_SETTINGS_KEY

from lasteverlm_account.repository_memory import MemoryRepository, _Usage

from .conftest import Clock

PRICES = "/api/account/prices"


def book(repo: MemoryRepository, clock: Clock, action: str, cost: str, **kw: object) -> None:
    repo.usage.append(
        _Usage(
            uuid.uuid4(),
            Decimal(cost),
            clock.now - timedelta(hours=1),
            action=action,
            action_id=uuid.uuid4(),
            **kw,  # type: ignore[arg-type]
        )
    )


def rules(repo: MemoryRepository, margin: int, fee: int = 0) -> None:
    repo.settings[PRICING_SETTINGS_KEY] = {
        "usd_per_eur": 1.1188,
        "default_margin_pct": margin,
        "actions": {"chat_answer": {"fixed_cents": fee}} if fee else {},
    }


def test_public_list_without_login_and_without_internals(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    rules(repo, 50, fee=1)
    for cost in ("2", "4", "6", "8", "10"):
        book(repo, clock, "chat_answer", cost, model="big")
    r = client.get(PRICES)
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=300"
    body = r.json()
    assert set(body) == {"usd_per_eur", "rate_date", "rate_source", "window_days", "actions"}
    row = next(a for a in body["actions"] if a["action"] == "chat_answer")
    assert set(row) == {"action", "unit", "price_per_unit_cents", "typical_cents", "count", "model"}
    # costs 2..10 through margin 50 % plus a 1-cent fee: 4, 7, 10, 13, 16
    assert row["unit"] == "question" and row["count"] == 5 and row["model"] == "big"
    assert row["typical_cents"] == {"p25": 7.0, "median": 10.0, "p75": 13.0}
    assert row["price_per_unit_cents"] == 10.0
    text = r.text
    for secret in ("margin", "fixed", "cost", "fee", "@"):
        assert secret not in text, secret
    assert all(a["action"] != "demo_seed" for a in body["actions"])


def test_no_number_below_five_actions(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    rules(repo, 0)
    for cost in ("1", "2", "3", "4"):
        book(repo, clock, "summary", cost)
    row = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "summary")
    assert (
        row["count"] == 4 and row["typical_cents"] is None and row["price_per_unit_cents"] is None
    )


def test_audio_is_priced_per_minute(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    rules(repo, 0)
    for minutes in (1, 2, 3, 4, 5):
        book(repo, clock, "output:audio", str(minutes * 10), kind="tts", tokens_in=minutes * 60)
    row = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "output:audio")
    assert row["unit"] == "audio_minute" and row["price_per_unit_cents"] == 10.0  # 10 ¢ a minute
    assert row["typical_cents"]["median"] == 30.0


def test_a_new_margin_shows_after_the_cache(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    rules(repo, 0)
    for _ in range(5):
        book(repo, clock, "chat_answer", "10")
    first = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "chat_answer")
    assert first["price_per_unit_cents"] == 10.0
    rules(repo, 100)
    cached = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "chat_answer")
    assert cached["price_per_unit_cents"] == 10.0  # within five minutes
    clock.advance(minutes=6)
    fresh = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "chat_answer")
    assert fresh["price_per_unit_cents"] == 20.0  # today's rules over the same measured costs


def test_old_actions_fall_out_of_the_window(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    rules(repo, 0)
    for _ in range(5):
        repo.usage.append(
            _Usage(
                uuid.uuid4(),
                Decimal(3),
                clock.now - timedelta(days=31),
                action="judge",
                action_id=uuid.uuid4(),
            )
        )
    row = next(a for a in client.get(PRICES).json()["actions"] if a["action"] == "judge")
    assert row["count"] == 0 and row["unit"] == "check"
