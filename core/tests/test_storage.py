"""The S3 storage against a stub client (what boto3 is asked to do), and
the presigned URL through a real boto3 client, which signs locally
without a request."""

from __future__ import annotations

import io
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from botocore.exceptions import ClientError

from lasteverlm_core import (
    PRESIGN_SECONDS,
    ConfigError,
    S3Settings,
    S3Storage,
    StorageError,
    object_key,
)

SETTINGS = S3Settings(
    endpoint="https://fra1.example.test",
    bucket="lasteverlm",
    access_key="access",
    secret_key="secret",
)


class StubClient:
    """Records every call; `fail` makes every call raise."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.objects: dict[str, bytes] = {}
        self.fail = fail
        self.head_error = "404"

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((name, kwargs))
        if self.fail:
            raise RuntimeError("endpoint unreachable")

    def put_object(self, **kwargs: Any) -> None:
        self._record("put_object", kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("get_object", kwargs)
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("head_object", kwargs)
        if kwargs["Key"] not in self.objects:
            code = self.head_error
            raise ClientError({"Error": {"Code": code, "Message": code}}, "HeadObject")
        return {"ContentLength": len(self.objects[kwargs["Key"]])}

    def delete_objects(self, **kwargs: Any) -> None:
        self._record("delete_objects", kwargs)

    def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str:
        self._record("generate_presigned_url", {"args": args, **kwargs})
        return f"https://signed/{kwargs['Params']['Key']}?e={kwargs['ExpiresIn']}"


def test_put_then_get_roundtrip() -> None:
    client = StubClient()
    storage = S3Storage(SETTINGS, client=client)
    storage.put("nb/out/audio.mp3", b"mp3", "audio/mpeg")
    assert storage.get("nb/out/audio.mp3") == b"mp3"
    assert client.calls[0] == (
        "put_object",
        {
            "Bucket": "lasteverlm",
            "Key": "nb/out/audio.mp3",
            "Body": b"mp3",
            "ContentType": "audio/mpeg",
        },
    )
    assert client.calls[1] == ("get_object", {"Bucket": "lasteverlm", "Key": "nb/out/audio.mp3"})


def test_delete_batches_by_thousand_and_skips_empty() -> None:
    client = StubClient()
    storage = S3Storage(SETTINGS, client=client)
    storage.delete()
    assert client.calls == []
    storage.delete(*[f"k{i}" for i in range(2500)])
    sizes = [len(kwargs["Delete"]["Objects"]) for _, kwargs in client.calls]
    assert sizes == [1000, 1000, 500]
    assert all(kwargs["Delete"]["Quiet"] for _, kwargs in client.calls)
    client.calls.clear()
    storage.delete("nb/out/audio.mp3")
    assert client.calls[0][1]["Delete"]["Objects"] == [{"Key": "nb/out/audio.mp3"}]


def test_presigned_get_defaults_to_one_hour() -> None:
    client = StubClient()
    storage = S3Storage(SETTINGS, client=client)
    assert PRESIGN_SECONDS == 3600
    assert storage.presigned_get("nb/out/audio.mp3") == "https://signed/nb/out/audio.mp3?e=3600"
    assert storage.presigned_get("k", expires_s=60).endswith("e=60")
    name, kwargs = client.calls[0]
    assert kwargs["args"] == ("get_object",)
    assert kwargs["Params"] == {"Bucket": "lasteverlm", "Key": "nb/out/audio.mp3"}
    with pytest.raises(ValueError):
        storage.presigned_get("k", expires_s=0)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda s: s.put("k", b"x", "text/plain"), "upload failed"),
        (lambda s: s.get("k"), "download failed"),
        (lambda s: s.delete("k"), "delete failed"),
        (lambda s: s.presigned_get("k"), "presign failed"),
    ],
)
def test_client_errors_become_storage_error(call: Any, message: str) -> None:
    storage = S3Storage(SETTINGS, client=StubClient(fail=True))
    with pytest.raises(StorageError, match=message):
        call(storage)


def test_real_boto3_presigns_locally() -> None:
    url = S3Storage(SETTINGS).presigned_get("nb/out/audio.mp3", expires_s=900)
    parsed = urlparse(url)
    assert parsed.netloc == "fra1.example.test"
    assert parsed.path == "/lasteverlm/nb/out/audio.mp3"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Expires"] == ["900"]
    assert "X-Amz-Signature" in query


def test_settings_from_env() -> None:
    env = {
        "S3_ENDPOINT": "https://fra1.example.test",
        "S3_BUCKET": "lasteverlm",
        "S3_ACCESS_KEY": "access",
        "S3_SECRET_KEY": "secret",
    }
    assert S3Settings.from_env(env) == SETTINGS
    assert S3Settings.from_env({**env, "S3_REGION": "eu-central-1"}).region == "eu-central-1"
    with pytest.raises(ConfigError, match="S3_BUCKET"):
        S3Settings.from_env({k: v for k, v in env.items() if k != "S3_BUCKET"})


def test_object_key() -> None:
    assert object_key("nb", "out", "audio.mp3") == "nb/out/audio.mp3"


def test_exists_is_false_only_for_a_missing_key() -> None:
    client = StubClient()
    storage = S3Storage(SETTINGS, client=client)
    storage.put("nb/voice/ryan.mp3", b"mp3", "audio/mpeg")
    assert storage.exists("nb/voice/ryan.mp3") is True
    assert storage.exists("nb/voice/eric.mp3") is False
    assert client.calls[-1] == ("head_object", {"Bucket": "lasteverlm", "Key": "nb/voice/eric.mp3"})
    client.head_error = "NoSuchKey"
    assert storage.exists("nb/voice/eric.mp3") is False


@pytest.mark.parametrize("code", ["403", "AccessDenied", "NoSuchBucket", "500"])
def test_exists_raises_on_any_other_error(code: str) -> None:
    client = StubClient()
    client.head_error = code
    with pytest.raises(StorageError, match="head failed"):
        S3Storage(SETTINGS, client=client).exists("nb/voice/eric.mp3")


def test_exists_raises_when_unreachable() -> None:
    with pytest.raises(StorageError, match="head failed"):
        S3Storage(SETTINGS, client=StubClient(fail=True)).exists("k")
