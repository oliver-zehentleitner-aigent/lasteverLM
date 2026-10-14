from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pytest

from lasteverlm_core import (
    DEFAULT_PRICING_RULES,
    PRICING_RULES_TTL_SECONDS,
    PRICING_SETTINGS_KEY,
    PRICING_SQL,
    ActionPricing,
    PricingRules,
    PricingRulesCache,
    estimate_charge,
)

from .conftest import FakeAsyncConnection, FakeConnection

RULES = {
    "default_margin_pct": 20,
    "actions": {
        "output:audio": {"margin_pct": 0, "fixed_cents": 5},
        "judge": {"margin_pct": 12.5},
        "source:pdf": {"fixed_cents": 0.5},
    },
}


def test_parse_reads_margins_and_fees() -> None:
    rules = PricingRules.parse(RULES)
    assert rules.margin_pct("chat_answer") == 20  # the default
    assert rules.margin_pct("output:audio") == 0  # its own, even 0
    assert rules.margin_pct("source:pdf") == 20  # a fee alone keeps the default margin
    assert rules.charge_cents("judge", Decimal(8)) == Decimal("9.000")
    assert rules.charge_cents("chat_answer", Decimal("0.33")) == Decimal("0.396")
    assert (rules.fixed_cents("output:audio"), rules.fixed_cents("judge")) == (
        Decimal(5),
        Decimal(0),
    )
    assert rules.fixed_cents("source:pdf") == Decimal("0.5")
    assert rules.as_json() == RULES
    assert PricingRules.parse(PricingRules.parse(RULES).as_json()) == rules
    assert PricingRules.parse('{"default_margin_pct": 0}') == DEFAULT_PRICING_RULES
    assert PricingRules.parse({}) == DEFAULT_PRICING_RULES
    assert DEFAULT_PRICING_RULES.charge_cents("judge", Decimal("0.1")) == Decimal("0.1")
    assert PRICING_SETTINGS_KEY == "pricing" and PRICING_RULES_TTL_SECONDS == 30


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "must be an object"),
        ({"margin": 1}, "unknown fields margin"),
        ({"default_margin_pct": -1}, "default_margin_pct must be between 0 and 1000"),
        ({"default_margin_pct": 1001}, "between 0 and 1000"),
        ({"default_margin_pct": "5"}, "must be a number"),
        ({"default_margin_pct": True}, "must be a number"),
        ({"actions": []}, "actions must be an object"),
        ({"actions": {"podcast": {}}}, "unknown action 'podcast'"),
        ({"actions": {"unknown": {}}}, "unknown action 'unknown'"),
        ({"actions": {"judge": 5}}, "must be an object"),
        ({"actions": {"judge": {"fee": 5}}}, "unknown fields fee"),
        ({"actions": {"judge": {"fixed_cents": 100_001}}}, "between 0 and 100000"),
        ({"actions": {"judge": {"margin_pct": None, "fixed_cents": -1}}}, "between 0"),
    ],
)
def test_parse_refuses_what_it_cannot_book(value: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PricingRules.parse(value)


def test_estimate_includes_the_fee_once(prices: Any) -> None:
    rules = PricingRules.parse(RULES)
    assert estimate_charge(prices, rules, "chat_answer", "llm", 1000, 2000) == Decimal("0.396")
    # tts at 0 margin plus the 5-cent fee
    assert estimate_charge(prices, rules, "output:audio", "llm", 1_000_000) == 35
    with pytest.raises(ValueError, match="unknown action"):
        estimate_charge(prices, rules, "unknown", "llm", 1)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_cache_reads_the_row_and_refreshes_after_the_ttl() -> None:
    clock = Clock()
    cache = PricingRulesCache(clock=clock)
    conn = FakeConnection(rows=[(RULES,), (None,)])
    assert cache.current(conn) == PricingRules.parse(RULES)
    assert conn.executed == [(PRICING_SQL, {"key": "pricing"})]
    clock.now = PRICING_RULES_TTL_SECONDS - 1
    assert cache.current(conn) == PricingRules.parse(RULES)  # cached
    clock.now = PRICING_RULES_TTL_SECONDS
    assert cache.current(conn) == DEFAULT_PRICING_RULES  # the row is gone
    assert len(conn.executed) == 2


def test_a_malformed_row_books_at_the_defaults_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = Clock()
    defaults = PricingRules(actions={"judge": ActionPricing(fixed_cents=Decimal(1))})
    cache = PricingRulesCache(defaults, clock=clock)
    bad = {"default_margin_pct": 5000}
    conn = FakeConnection(rows=[(bad,), (bad,), ('{"default_margin_pct": 1}',)])
    with caplog.at_level(logging.WARNING, logger="lasteverlm_core.billing"):
        for i in range(2):
            clock.now = i * PRICING_RULES_TTL_SECONDS
            assert cache.current(conn) == defaults
    assert len(caplog.records) == 1 and "between 0 and 1000" in caplog.text
    clock.now = 2 * PRICING_RULES_TTL_SECONDS
    assert cache.current(conn).default_margin_pct == 1


def test_a_failing_read_is_raised_not_hidden() -> None:
    class Broken(FakeConnection):
        def __init__(self) -> None:
            super().__init__()
            self._cursor.execute = self._fail  # type: ignore[method-assign]

        @staticmethod
        def _fail(*_: Any) -> None:
            raise RuntimeError("relation settings does not exist")

    with pytest.raises(RuntimeError, match="settings"):
        PricingRulesCache().current(Broken())


async def test_async_cache() -> None:
    conn = FakeAsyncConnection(rows=[({"default_margin_pct": 10},)])
    cache = PricingRulesCache()
    assert (await cache.acurrent(conn)).default_margin_pct == 10
    assert (await cache.acurrent(conn)).default_margin_pct == 10
    assert len(conn.executed) == 1
