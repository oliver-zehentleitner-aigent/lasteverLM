import pytest

from lasteverlm_ingest.config import ConfigError
from tests.conftest import make_settings


def test_defaults_and_values():
    s = make_settings(CHUNK_TOKENS="", CHUNK_OVERLAP_TOKENS="", MAX_UPLOAD_BYTES="")
    assert s.chunk_tokens == 800
    assert s.chunk_overlap_tokens == 100
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert s.demo_token == "test-demo-token"
    assert s.auth_jwt_secret is None


def test_missing_required_variable_names_it():
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        make_settings(DATABASE_URL="")


def test_at_least_one_auth_scheme():
    both = make_settings(AUTH_JWT_SECRET="x" * 32)
    assert both.auth_jwt_secret and both.demo_token
    with pytest.raises(ConfigError, match="AUTH_JWT_SECRET and/or DEMO_TOKEN"):
        make_settings(DEMO_TOKEN="")


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ConfigError, match="CHUNK_OVERLAP_TOKENS"):
        make_settings(CHUNK_TOKENS="100", CHUNK_OVERLAP_TOKENS="100")


def test_model_prices_parsing():
    s = make_settings(
        MODEL_PRICES='{"fake-embed": {"in": 1.5, "out": 0}, "fake-llm": {"in": 1, "out": 2}}'
    )
    assert (s.model_prices["fake-embed"].cents_in, s.model_prices["fake-embed"].cents_out) == (
        1.5,
        0.0,
    )
    with pytest.raises(ConfigError, match="no price"):
        make_settings(MODEL_PRICES="")
    with pytest.raises(ConfigError, match="no price .* 'fake-embed', 'fake-llm'"):
        make_settings(MODEL_PRICES='{"other": {"in": 1, "out": 0}}')
    with pytest.raises(ConfigError, match="no price .* 'fake-llm'"):
        make_settings(MODEL_PRICES='{"fake-embed": {"in": 1, "out": 0}}')
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        make_settings(MODEL_PRICES="[1]")
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        make_settings(MODEL_PRICES='{"m": {"in": 1}}')


def test_non_integer_is_rejected():
    with pytest.raises(ConfigError, match="EMBEDDING_DIMENSION"):
        make_settings(EMBEDDING_DIMENSION="many")
