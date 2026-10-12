import pytest

from lasteverlm_rag.config import ConfigError, Settings
from lasteverlm_rag.contracts import (
    ModelPrice,
    UnpricedModelError,
    cost_cents,
    parse_model_prices,
)

from .conftest import BASE_ENV


def test_cost_is_ceiled_cents_per_million_tokens():
    prices = parse_model_prices('{"m": {"in": 100, "out": 300}}')
    assert prices == {"m": ModelPrice.model_validate({"in": 100, "out": 300})}
    assert cost_cents(prices, "m", 1_000_000, 0) == 100
    assert cost_cents(prices, "m", 500_000, 100_000) == 80
    assert cost_cents(prices, "m", 1, 0) == 1  # never free once tokens were used
    with pytest.raises(UnpricedModelError):
        cost_cents(prices, "unknown", 10, 10)


def test_settings_refuse_a_configured_model_without_price():
    with pytest.raises(ConfigError, match="no price for configured model.*'test-llm'"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": ""})
    with pytest.raises(ConfigError, match="no price for configured model.*'tts-1'"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "TTS_MODEL": "tts-1"})
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": '{"test-llm": 3}'})
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": "[1]"})
