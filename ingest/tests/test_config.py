import pytest
from lasteverlm_core.settings import VULTR_INFERENCE_BASE_URL

from lasteverlm_ingest.config import ConfigError
from tests.conftest import make_settings


def test_defaults_and_values():
    s = make_settings(CHUNK_TOKENS="", CHUNK_OVERLAP_TOKENS="", MAX_UPLOAD_BYTES="")
    assert s.chunk_tokens is None and s.chunk_overlap_tokens is None  # core decides
    assert s.chunker_kwargs() == {}
    assert make_settings(CHUNK_TOKENS="300", CHUNK_OVERLAP_TOKENS="").chunker_kwargs() == {
        "size": 300
    }
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert s.stt_timeout_seconds == 300 and s.inference.stt_model == "fake-stt"
    assert s.auth.demo_token == "test-demo-token"
    assert s.auth.jwt_secret is None
    assert s.inference.embedding_dimension == 8 and s.inference.llm_model == "fake-llm"
    assert s.rate_limit.per_minute == 1000


def test_inference_base_url_defaults_to_the_platform():
    base_url = make_settings(INFERENCE_BASE_URL="").inference.base_url
    assert base_url == VULTR_INFERENCE_BASE_URL


def test_missing_required_variable_names_it():
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        make_settings(DATABASE_URL="")


def test_at_least_one_auth_scheme():
    both = make_settings(AUTH_JWT_SECRET="x" * 32)
    assert both.auth.jwt_secret and both.auth.demo_token
    with pytest.raises(ConfigError, match="AUTH_JWT_SECRET or DEMO_TOKEN"):
        make_settings(DEMO_TOKEN="")


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ConfigError, match="CHUNK_OVERLAP_TOKENS"):
        make_settings(CHUNK_TOKENS="100", CHUNK_OVERLAP_TOKENS="100")


def test_model_prices_parsing():
    s = make_settings(
        MODEL_PRICES='{"fake-embed": {"in": 1.5, "out": 0}, "fake-llm": {"in": 1, "out": 2},'
        ' "fake-stt": {"in": 1, "out": 0}}'
    )
    assert (s.model_prices["fake-embed"].cents_in, s.model_prices["fake-embed"].cents_out) == (
        1.5,
        0.0,
    )
    with pytest.raises(ConfigError, match="no price"):
        make_settings(MODEL_PRICES="")
    with pytest.raises(ConfigError, match="no price configured for model 'fake-embed'"):
        make_settings(MODEL_PRICES='{"other": {"in": 1, "out": 0}}')
    with pytest.raises(ConfigError, match="no price configured for model 'fake-llm'"):
        make_settings(MODEL_PRICES='{"fake-embed": {"in": 1, "out": 0}}')
    with pytest.raises(ConfigError, match="no price configured for model 'fake-stt'"):
        make_settings(
            MODEL_PRICES='{"fake-embed": {"in": 1, "out": 0}, "fake-llm": {"in": 1, "out": 0}}'
        )
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        make_settings(MODEL_PRICES="[1]")
    with pytest.raises(ConfigError, match="MODEL_PRICES"):
        make_settings(MODEL_PRICES='{"m": {"in": 1}}')


def test_non_integer_is_rejected():
    with pytest.raises(ConfigError, match="EMBEDDING_DIMENSION"):
        make_settings(EMBEDDING_DIMENSION="many")


def test_stt_timeout_stays_below_the_claim_timeout():
    assert make_settings(STT_TIMEOUT_SECONDS="599").stt_timeout_seconds == 599
    for value in ("600", "0"):
        with pytest.raises(ConfigError, match="STT_TIMEOUT_SECONDS"):
            make_settings(STT_TIMEOUT_SECONDS=value)
