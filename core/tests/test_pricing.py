from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from lasteverlm_core import (
    ConfigError,
    ModelPrice,
    UnpricedModelError,
    cost_cents,
    load_model_prices,
    parse_model_prices,
    require_prices,
)


def test_cost_is_ceil_of_cents_per_million(prices: Any) -> None:
    # 1000 in * 30 + 2000 out * 150 = 330_000 / 1e6 = 0.33 cents -> 1
    assert cost_cents(prices, "llm", 1000, 2000) == 1
    assert cost_cents(prices, "llm", 1_000_000, 0) == 30
    assert cost_cents(prices, "llm", 1_000_001, 0) == 31
    assert cost_cents(prices, "embed", 0, 0) == 0


def test_fractional_prices_are_exact() -> None:
    prices = parse_model_prices('{"m": {"in": 0.1, "out": 0.2}}')
    assert cost_cents(prices, "m", 1_000_000, 0) == 1
    assert cost_cents(prices, "m", 3_000_000, 1_000_000) == 1  # 0.3 + 0.2 = 0.5 -> 1
    assert cost_cents(prices, "m", 10_000_000, 0) == 1


def test_unpriced_model_raises_instead_of_zero(prices: Any) -> None:
    with pytest.raises(UnpricedModelError) as exc:
        cost_cents(prices, "mystery", 10, 10)
    assert exc.value.model == "mystery"
    assert isinstance(exc.value, ConfigError)


def test_negative_tokens_rejected(prices: Any) -> None:
    with pytest.raises(ValueError):
        cost_cents(prices, "llm", -1, 0)


def test_require_prices_fails_loud_at_startup(prices: Any) -> None:
    require_prices(prices, ["llm", "embed"])
    with pytest.raises(UnpricedModelError):
        require_prices(prices, ["llm", "other"])


def test_parse_merges_over_defaults() -> None:
    defaults = {"a": ModelPrice.model_validate({"in": 1, "out": 1})}
    merged = parse_model_prices('{"b": {"in": 2, "out": 3}, "a": {"in": 5, "out": 5}}', defaults)
    assert set(merged) == {"a", "b"}
    assert merged["a"].cents_in == Decimal(5)
    assert merged["b"].cents_out == Decimal(3)
    assert parse_model_prices(None, defaults) == defaults
    assert parse_model_prices("  ", defaults) == defaults


@pytest.mark.parametrize(
    "raw",
    ["not json", "[1, 2]", '{"m": {"in": 1}}', '{"m": {"in": -1, "out": 0}}', '{"m": 5}'],
)
def test_parse_rejects_bad_shapes(raw: str) -> None:
    with pytest.raises(ConfigError):
        parse_model_prices(raw)


def test_load_from_env() -> None:
    prices = load_model_prices({"MODEL_PRICES": '{"m": {"in": 1, "out": 2}}'})
    assert prices["m"].cents_out == Decimal(2)
    assert load_model_prices({}) == {}
