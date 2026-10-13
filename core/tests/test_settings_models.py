from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from lasteverlm_core import (
    Citation,
    ConfigError,
    InferenceSettings,
    Message,
    Output,
    SharedOutput,
    env_int,
    env_optional,
    env_required,
)


def test_env_helpers_fail_loud() -> None:
    env = {"A": " x ", "B": "", "N": "12", "BAD": "twelve"}
    assert env_required("A", env) == "x"
    assert env_optional("B", env) is None
    assert env_int("N", 1, env) == 12
    assert env_int("MISSING", 1, env) == 1
    with pytest.raises(ConfigError, match="B is required"):
        env_required("B", env)
    with pytest.raises(ConfigError, match="BAD must be an integer"):
        env_int("BAD", 1, env)


def test_inference_settings_from_env() -> None:
    env = {"INFERENCE_API_KEY": "k", "LLM_MODEL": "l", "EMBEDDING_MODEL": "e"}
    settings = InferenceSettings.from_env(env)
    assert settings.base_url == "https://api.vultrinference.com/v1"
    assert settings.embedding_dimension == 1536
    assert settings.llm_max_tokens == 1024
    assert InferenceSettings.from_env({**env, "LLM_MAX_TOKENS": "400"}).llm_max_tokens == 400
    with pytest.raises(ConfigError, match="INFERENCE_API_KEY"):
        InferenceSettings.from_env({})


def test_output_options_default_to_empty() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "audio",
        "title": "t",
        "status": "ready",
        "created_at": "2026-10-13T00:00:00Z",
    }
    assert Output.model_validate(row).options == {}
    options = {"language": "de", "voice": "ryan", "speed": 1.0}
    assert Output.model_validate({**row, "options": options}).options == options
    shared = SharedOutput(kind="audio", title="t", created_at=datetime(2026, 10, 13, tzinfo=UTC))
    assert shared.options == {}


def test_models_serialize_ids_and_times_as_strings() -> None:
    message = Message(
        id=uuid4(),
        role="assistant",
        content="hi [1]",
        citations=[
            Citation(
                n=1,
                source_id=uuid4(),
                source_name="a.pdf",
                source_kind="pdf",
                chunk_id=uuid4(),
                page=3,
                quote="…",
            )
        ],
        created_at=datetime(2026, 10, 12, tzinfo=UTC),
    )
    wire = json.loads(message.model_dump_json())
    assert wire["id"] == str(message.id)
    assert wire["created_at"].startswith("2026-10-12")
    assert wire["citations"][0]["source_kind"] == "pdf"
    assert Message.model_validate(wire) == message
