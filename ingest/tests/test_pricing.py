import pytest

from lasteverlm_ingest.contracts import (
    UnpricedModelError,
    cost_cents,
    parse_model_prices,
    require_prices,
)

PRICES = parse_model_prices('{"embed": {"in": 2000, "out": 0}, "llm": {"in": 300, "out": 1500}}')


@pytest.mark.parametrize(
    ("model", "tokens_in", "tokens_out", "cents"),
    [
        ("embed", 0, 0, 0),
        ("embed", 1, 0, 1),  # a fraction of a cent is still a cent
        ("embed", 1_000_000, 0, 2000),
        ("embed", 499_999, 0, 1000),
        ("llm", 1_000_000, 1_000_000, 1800),
    ],
)
def test_cost_rounds_up_per_model(model, tokens_in, tokens_out, cents):
    assert cost_cents(PRICES, model, tokens_in, tokens_out) == cents


def test_unpriced_model_is_refused_not_free():
    with pytest.raises(UnpricedModelError):
        cost_cents(PRICES, "unpriced", 10, 0)
    with pytest.raises(UnpricedModelError, match="'unpriced'"):
        require_prices(PRICES, ["embed", "unpriced"])
    require_prices(PRICES, ["embed", "llm"])


def test_negative_price_is_rejected():
    with pytest.raises(ValueError, match="MODEL_PRICES"):
        parse_model_prices('{"m": {"in": -1, "out": 0}}')
