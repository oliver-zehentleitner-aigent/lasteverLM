"""The public price list: per-unit prices from rag's and ingest's estimates, the typical
range from history, end prices only, no login."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
import jwt as pyjwt
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, PRICING_SETTINGS_KEY

from lasteverlm_account.repository_memory import MemoryRepository, _Usage
from lasteverlm_account.services import EstimateClient

from .conftest import Clock

PRICES = "/api/account/prices"


class FakeEstimates:
    """rag: min = 2 + judge level index, max = min + 2; chart parts add up. ingest: 0.5 per
    unit, vision 3. Records the bearer and fails on demand."""

    def __init__(self) -> None:
        self.bearers: list[str] = []
        self.fail_ingest = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bearers.append(request.headers.get("authorization", ""))
        if request.url.path == "/api/rag/estimate":
            body = json.loads(request.content)
            low = 2.0
            if body.get("action") == "judge":
                low = {"low": 1.0, "medium": 3.0, "high": 10.0}[body["options"]["level"]]
            if body.get("kind") == "chart":
                low = 0.5
            return httpx.Response(
                200,
                json={
                    "charge_cents_min": low,
                    "charge_cents_max": low + 2,
                    "cost_eur_cents_min": 999,
                },
            )
        if request.url.path == "/api/ingest/estimate":
            if self.fail_ingest:
                return httpx.Response(503)
            kind = request.url.params["kind"]
            assert kind in {"text", "url", "pdf_text", "pdf_vision", "image", "audio"}
            return httpx.Response(
                200,
                json={
                    "kind": kind,
                    "charge_cents": "3.0" if kind == "pdf_vision" else "0.5",
                    "per_source_charge_cents": "1.25",
                    "cost_cents": "999",
                },
            )
        return httpx.Response(404)


def install(client: TestClient) -> FakeEstimates:
    fake = FakeEstimates()
    client.app.state.service.estimates = EstimateClient(  # type: ignore[attr-defined]
        ingest_url="http://ingest", rag_url="http://rag", transport=httpx.MockTransport(fake)
    )
    return fake


def rows(client: TestClient) -> dict[str, dict[str, object]]:
    return {a["action"]: a for a in client.get(PRICES).json()["actions"]}


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


def test_every_row_has_an_estimated_price_without_history(client: TestClient) -> None:
    fake = install(client)
    r = client.get(PRICES)
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=300"
    got = rows(client)
    chat = got["chat_answer"]
    assert (chat["unit"], chat["estimated"]) == ("question", True)
    assert (chat["price_min_cents"], chat["price_max_cents"], chat["price_per_unit_cents"]) == (
        2,
        4,
        3,
    )
    assert chat["typical_cents"] is None and chat["count"] == 0
    assert got["output:report"]["unit"] == "output" and got["output:report"]["estimated"]
    assert got["output:chart"]["price_min_cents"] == 2.5  # chart_propose 2 + chart 0.5
    assert got["judge:high"]["price_per_unit_cents"] == 11 and got["judge:high"]["level"] == "high"
    assert got["source:pdf"]["unit"] == "page" and got["source:pdf"]["price_per_unit_cents"] == 0.5
    assert got["source:pdf:vision"]["price_per_unit_cents"] == 3
    assert got["source:pdf"]["per_source_cents"] == 1.25 and chat["per_source_cents"] is None
    assert got["source:audio"]["unit"] == "audio_minute"
    assert "demo_seed" not in got and "judge" not in got
    # no internals: the fake's cost field never reaches the public body
    for secret in ("cost", "margin", "fee", "999", "@"):
        assert secret not in r.text, secret
    # account calls as the demo user with a short-lived token
    claims = pyjwt.decode(
        fake.bearers[0].removeprefix("Bearer "), options={"verify_signature": False}
    )
    assert claims["sub"] == str(DEMO_USER_ID) and claims["exp"] - claims["iat"] == 60


def test_a_failed_estimate_leaves_the_price_empty(client: TestClient) -> None:
    fake = install(client)
    fake.fail_ingest = True
    got = rows(client)
    assert (
        got["source:pdf"]["price_per_unit_cents"] is None
        and got["source:pdf"]["estimated"] is False
    )
    assert got["chat_answer"]["estimated"] is True


def test_typical_range_comes_from_history(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    install(client)
    repo.settings[PRICING_SETTINGS_KEY] = {
        "usd_per_eur": 1.1188,
        "default_margin_pct": 50,
        "actions": {},
    }
    for cost in ("2", "4", "6", "8", "10"):
        book(repo, clock, "chat_answer", cost, model="big")
    chat = rows(client)["chat_answer"]
    assert chat["typical_cents"] == {"p25": 6.0, "median": 9.0, "p75": 12.0}  # cost × 1.5
    assert chat["count"] == 5 and chat["model"] == "big"
    assert chat["price_per_unit_cents"] == 3  # still the estimate, not history


def test_judge_history_is_split_per_level(
    client: TestClient, repo: MemoryRepository, clock: Clock
) -> None:
    install(client)
    repo.settings[PRICING_SETTINGS_KEY] = {
        "usd_per_eur": 1.1188,
        "default_margin_pct": 0,
        "actions": {},
    }
    models = client.app.state.service.settings.judge_models  # type: ignore[attr-defined]
    for _ in range(5):
        book(repo, clock, "judge", "1", model=models["low"])
    got = rows(client)
    assert got["judge:low"]["count"] == 5 and got["judge:low"]["typical_cents"]["median"] == 1.0
    assert got["judge:high"]["count"] == 0


def test_cached_five_minutes(client: TestClient, clock: Clock) -> None:
    fake = install(client)
    client.get(PRICES)
    calls = len(fake.bearers)
    client.get(PRICES)
    assert len(fake.bearers) == calls
    clock.advance(minutes=6)
    client.get(PRICES)
    assert len(fake.bearers) > calls
