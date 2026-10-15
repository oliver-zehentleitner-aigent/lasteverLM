from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lasteverlm_core import (
    DEFAULT_JUDGE_MODELS,
    JUDGE_LEVELS,
    UNKNOWN_BUILD,
    USAGE_ACTION_UNITS,
    ActionUnit,
    Answer,
    ChunkView,
    Citation,
    ConfigError,
    Health,
    InferenceSettings,
    Message,
    MessageFeedback,
    Output,
    OutputKind,
    SharedOutput,
    Source,
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
    assert settings.stt_model == "whisper-large-v3-turbo"
    assert InferenceSettings.from_env({**env, "LLM_MAX_TOKENS": "400"}).llm_max_tokens == 400
    assert InferenceSettings.from_env({**env, "STT_MODEL": " stt "}).stt_model == "stt"
    with pytest.raises(ConfigError, match="INFERENCE_API_KEY"):
        InferenceSettings.from_env({})


def test_judge_models_default_and_merge_per_level() -> None:
    env = {"INFERENCE_API_KEY": "k", "LLM_MODEL": "l", "EMBEDDING_MODEL": "e"}
    assert JUDGE_LEVELS == ("low", "medium", "high")
    assert (
        InferenceSettings.from_env(env).judge_models
        == DEFAULT_JUDGE_MODELS
        == {
            "low": "deepseek-v4.1-flash",
            "medium": "glm-5.3-flash",
            "high": "glm-5.3",
        }
    )
    custom = InferenceSettings.from_env({**env, "JUDGE_MODELS": '{"high": " clef "}'})
    assert custom.judge_models == {**DEFAULT_JUDGE_MODELS, "high": "clef"}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{", "not valid JSON"),
        ('["glm-5.3"]', "JSON object keyed by level"),
        ('{"extreme": "glm-5.3"}', "unknown level 'extreme'"),
        ('{"low": ""}', r"JUDGE_MODELS\['low'\] must be a model name"),
        ('{"low": 3}', r"JUDGE_MODELS\['low'\] must be a model name"),
    ],
)
def test_bad_judge_models_fail_at_startup(raw: str, message: str) -> None:
    env = {"INFERENCE_API_KEY": "k", "LLM_MODEL": "l", "EMBEDDING_MODEL": "e"}
    with pytest.raises(ConfigError, match=message):
        InferenceSettings.from_env({**env, "JUDGE_MODELS": raw})


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


def test_an_output_outlives_its_notebook_and_can_sit_in_the_trash() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "report",
        "title": "t",
        "status": "ready",
        "created_at": "2026-10-14T00:00:00Z",
    }
    live = Output.model_validate(row)
    assert (live.origin_title, live.deleted_at, live.purge_at) == ("", None, None)
    orphan = Output.model_validate(
        {
            **row,
            "notebook_id": None,
            "origin_title": "Quartalsbericht",
            "deleted_at": "2026-10-14T10:00:00Z",
            "purge_at": "2026-10-28T10:00:00Z",
        }
    )
    assert orphan.notebook_id is None and orphan.origin_title == "Quartalsbericht"
    assert orphan.purge_at == datetime(2026, 10, 28, 10, tzinfo=UTC)
    wire = orphan.model_dump(mode="json")
    assert wire["notebook_id"] is None and wire["deleted_at"] == "2026-10-14T10:00:00Z"
    assert "owner" not in wire and "user_id" not in wire  # always the caller
    assert set(SharedOutput.model_fields) == {
        "kind",
        "title",
        "content",
        "options",
        "created_at",
        "provenance",
    }


def test_phase_is_optional_and_passed_through() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "report",
        "title": "t",
        "status": "processing",
        "created_at": "2026-10-15T00:00:00Z",
    }
    assert Output.model_validate(row).phase is None
    phase = {"step": "writing", "since": "2026-10-15T00:00:05Z", "n": 2, "of": 5}
    assert Output.model_validate({**row, "phase": phase}).model_dump(mode="json")["phase"] == phase
    assert "phase" not in SharedOutput.model_fields  # a shared output is always ready


def test_provenance_is_optional_and_passed_through() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "report",
        "title": "t",
        "status": "ready",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert Output.model_validate(row).provenance is None
    log = {"units": [{"text": "a", "chunks": ["c1"]}], "checked": True}
    assert Output.model_validate({**row, "provenance": log}).provenance == log
    shared = SharedOutput(
        kind="report", title="t", created_at=datetime(2026, 10, 14, tzinfo=UTC), provenance=log
    )
    assert shared.model_dump(mode="json")["provenance"] == log
    assert SharedOutput(kind="report", title="t", created_at=shared.created_at).provenance is None


def test_support_check_on_messages_and_answers_is_optional() -> None:
    row = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": "a [1]",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert (Message.model_validate(row).units, Message.model_validate(row).check) == (None, None)
    units = [{"text": "a [1]", "refs": [1], "support": "supported"}]
    check = {
        "method": "overlap",
        "threshold": 0.5,
        "supported": 1,
        "unsupported": 0,
        "unverified": 0,
    }
    message = Message.model_validate({**row, "units": units, "check": check})
    assert message.model_dump(mode="json")["units"] == units
    answer = Answer(message_id=uuid4(), answer="a [1]", units=units, check=check)
    assert answer.check == check
    assert Answer(message_id=uuid4(), answer="a").units is None


def test_suggestions_and_feedback_are_optional_and_bounded() -> None:
    row = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": "a [1]",
        "created_at": "2026-10-14T00:00:00Z",
    }
    old = Message.model_validate(row)
    assert (old.suggestions, old.feedback) == ([], None)
    assert Message.model_validate({**row, "suggestions": None}).suggestions == []
    feedback = {"rating": "down", "comment": "wrong year", "at": "2026-10-14T10:00:00Z"}
    message = Message.model_validate(
        {**row, "suggestions": ["Why?", "Since when?"], "feedback": feedback}
    )
    assert message.feedback == MessageFeedback(
        rating="down", comment="wrong year", at=datetime(2026, 10, 14, 10, tzinfo=UTC)
    )
    wire = message.model_dump(mode="json")
    assert wire["suggestions"] == ["Why?", "Since when?"]
    assert wire["feedback"] == {**feedback, "at": "2026-10-14T10:00:00Z"}
    with pytest.raises(ValidationError):
        Message.model_validate({**row, "suggestions": ["a", "b", "c", "d"]})
    with pytest.raises(ValidationError):
        MessageFeedback.model_validate({"rating": "meh", "at": "2026-10-14T10:00:00Z"})
    assert Answer(message_id=uuid4(), answer="a").suggestions == []
    assert Answer(message_id=uuid4(), answer="a", suggestions=["Why?"]).suggestions == ["Why?"]


def test_web_pages_default_to_empty_and_pass_through() -> None:
    row = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": "a [1]",
        "created_at": "2026-10-15T00:00:00Z",
    }
    assert Message.model_validate(row).web_pages == []
    assert Message.model_validate({**row, "web_pages": None}).web_pages == []
    pages = [{"library_id": str(uuid4()), "name": "example.org", "fetched_at": None}]
    assert Message.model_validate({**row, "web_pages": pages}).web_pages == pages
    assert Answer(message_id=uuid4(), answer="a").web_pages == []
    assert Answer(message_id=uuid4(), answer="a", web_pages=pages).web_pages == pages


def test_a_plan_is_optional_and_passed_through() -> None:
    row = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": "",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert Message.model_validate(row).plan is None
    plan = {"plan_id": "p1", "status": "proposed", "steps": [], "estimate": {"min": 1, "max": 2}}
    assert Message.model_validate({**row, "plan": plan}).model_dump(mode="json")["plan"] == plan
    assert Answer(message_id=uuid4(), answer="", plan=plan).plan == plan
    assert Answer(message_id=uuid4(), answer="a").plan is None


def test_a_source_can_be_added_without_being_read() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "name": "a.pdf",
        "kind": "pdf",
        "status": "added",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert Source.model_validate(row).status == "added"


def test_a_source_can_wait_for_credit() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "name": "a.pdf",
        "kind": "pdf",
        "status": "waiting_for_credit",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert Source.model_validate(row).status == "waiting_for_credit"


def test_flashcards_are_an_output_kind_billed_per_output() -> None:
    assert "flashcards" in get_args(OutputKind)
    assert USAGE_ACTION_UNITS["output:flashcards"] == ActionUnit("output", "action")


def test_chart_is_an_output_kind() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "chart",
        "title": "t",
        "status": "ready",
        "created_at": "2026-10-14T00:00:00Z",
    }
    assert Output.model_validate(row).kind == "chart"


def test_health_reports_the_build_from_the_env() -> None:
    env = {"APP_VERSION": "0.4.0", "APP_COMMIT": " 5e320ae "}
    assert Health.from_env(env).model_dump() == {
        "status": "ok",
        "version": "0.4.0",
        "commit": "5e320ae",
    }
    unset = Health.from_env({"APP_COMMIT": ""})
    assert (unset.version, unset.commit) == (UNKNOWN_BUILD, "unknown")


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


@pytest.mark.parametrize("name", ["LLM_MAX_TOKENS", "EMBEDDING_DIMENSION", "LLM_TIMEOUT_SECONDS"])
def test_inference_widths_below_one_fail_at_startup(name: str) -> None:
    env = {"INFERENCE_API_KEY": "k", "LLM_MODEL": "l", "EMBEDDING_MODEL": "e", name: "0"}
    with pytest.raises(ConfigError, match=f"{name} must be at least 1"):
        InferenceSettings.from_env(env)
