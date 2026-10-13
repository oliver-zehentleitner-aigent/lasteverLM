from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lasteverlm_core import (
    ChunkView,
    Citation,
    ConfigError,
    InferenceSettings,
    Message,
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


def test_citation_provenance_fields_are_optional() -> None:
    stored = {
        "n": 1,
        "source_id": str(uuid4()),
        "source_name": "a.pdf",
        "source_kind": "pdf",
        "chunk_id": str(uuid4()),
        "page": None,
        "quote": "old",
    }
    old = Citation.model_validate(stored)
    assert (old.similarity, old.chunk_index, old.chunk_count) == (None, None, None)
    new = Citation.model_validate(
        {**stored, "similarity": 0.812, "chunk_index": 0, "chunk_count": 7}
    )
    assert json.loads(new.model_dump_json())["chunk_index"] == 0
    with pytest.raises(ValidationError):
        Citation.model_validate({**stored, "chunk_index": -1})


def test_chunk_view_round_trips() -> None:
    view = ChunkView(
        chunk_id=uuid4(),
        source_id=uuid4(),
        source_name="a.pdf",
        source_kind="pdf",
        page=2,
        chunk_index=3,
        chunk_count=9,
        text="full chunk",
    )
    assert ChunkView.model_validate(json.loads(view.model_dump_json())) == view
