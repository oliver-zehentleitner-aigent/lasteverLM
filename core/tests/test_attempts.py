from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from lasteverlm_core import (
    MAX_ATTEMPT_MESSAGE,
    AttemptRecord,
    Output,
    ProviderError,
    UnpricedModelError,
    short_id,
)

AT = datetime(2026, 10, 15, 12, tzinfo=UTC)


def test_short_id_is_the_first_eight_hex_characters() -> None:
    value = UUID("3F2A9C1E-1234-4567-89AB-0123456789AB")
    assert short_id(value) == "3f2a9c1e"
    assert short_id(str(value)) == "3f2a9c1e"
    assert short_id("3f2a9c1e123445678 9ab0123456789ab".replace(" ", "")) == "3f2a9c1e"
    with pytest.raises(ValueError):
        short_id("not-a-uuid")


def test_an_attempt_record_round_trips_and_keeps_one_short_line() -> None:
    record = AttemptRecord(
        at=AT,
        attempt=2,
        model="qwen",
        error_kind="provider",
        provider_status=503,
        message="completion\nrequest   failed:\tHTTP 503",
        service="rag",
    )
    assert record.message == "completion request failed: HTTP 503"
    assert AttemptRecord.model_validate(record.model_dump(mode="json")) == record
    long = AttemptRecord(
        at=AT, attempt=1, error_kind="internal", message="x" * 900, service="ingest"
    )
    assert len(long.message) == MAX_ATTEMPT_MESSAGE
    for bad in ({"attempt": 0}, {"provider_status": 42}, {"error_kind": ""}, {"service": "web"}):
        with pytest.raises(ValidationError):
            AttemptRecord.model_validate(
                {"at": AT, "attempt": 1, "error_kind": "internal", "service": "rag", **bad}
            )


def test_from_error_keeps_core_text_only() -> None:
    refused = ProviderError(
        "completion request failed: Error code: 400 - {'detail': 'the prompt was ...'}",
        permanent=True,
        status=400,
        summary="completion request failed: HTTP 400",
    )
    record = AttemptRecord.from_error(refused, attempt=1, service="rag", model="m", at=AT)
    assert (record.error_kind, record.provider_status) == ("provider_refused", 400)
    assert record.message == "completion request failed: HTTP 400"  # no provider text
    retry = AttemptRecord.from_error(
        ProviderError("provider returned an empty answer"), attempt=3, service="rag"
    )
    assert (retry.error_kind, retry.provider_status, retry.message) == (
        "provider",
        None,
        "provider returned an empty answer",
    )
    assert retry.at.tzinfo is not None
    config = AttemptRecord.from_error(UnpricedModelError("m"), attempt=1, service="ingest")
    assert config.error_kind == "configuration" and "MODEL_PRICES" in config.message
    timeout = AttemptRecord.from_error(
        TimeoutError("read of chunk 7: <source text>"), attempt=1, service="ingest"
    )
    assert (timeout.error_kind, timeout.message) == ("timeout", "TimeoutError")
    other = AttemptRecord.from_error(KeyError("Dear reader, ..."), attempt=1, service="rag")
    assert (other.error_kind, other.message) == ("internal", "KeyError")  # never the text


def test_an_output_carries_its_attempt_log() -> None:
    row = {
        "id": str(uuid4()),
        "notebook_id": str(uuid4()),
        "kind": "report",
        "title": "t",
        "status": "failed",
        "created_at": "2026-10-15T00:00:00Z",
    }
    assert Output.model_validate(row).attempt_log == []
    assert Output.model_validate({**row, "attempt_log": None}).attempt_log == []
    entry = {
        "at": "2026-10-15T12:00:00Z",
        "attempt": 1,
        "model": "qwen",
        "error_kind": "provider",
        "provider_status": None,
        "message": "completion request failed: HTTP 503",
        "service": "rag",
    }
    output = Output.model_validate({**row, "attempt_log": [entry]})
    assert output.attempt_log[0].provider_status is None
    assert output.model_dump(mode="json")["attempt_log"] == [entry]
