"""Object storage for uploads and generated files, behind one interface.

The implementation is an S3 client (boto3) pointed at Vultr Object
Storage, one bucket for the whole family. Object keys follow the family
contract: `<user_id>/<library_source_id>/<name>` for an upload (sources
live in the user's library, not in one notebook),
`<notebook_id>/<output_id>/<name>` for a file an output produces.

A presigned GET is how a browser fetches a private object without a
bearer header (an `<audio>` element cannot send one); the URL carries its
own expiry and needs no further call to storage. With a `download_name`
it also carries the `Content-Disposition` the response is served with,
because a link's `download` attribute is ignored across origins.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import ClientError

from .settings import env_optional, env_required

PRESIGN_SECONDS = 3600
# SigV4 caps a presigned URL at seven days; a longer one is refused by S3.
PRESIGN_MAX_SECONDS = 7 * 24 * 3600
DEFAULT_S3_REGION = "us-east-1"
# What S3 implementations answer a HEAD on a missing key with.
MISSING_KEY_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class StorageError(Exception):
    """An object-storage request failed."""


class Storage(Protocol):
    """The object store callers are typed against; `S3Storage` implements it."""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, *keys: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def presigned_get(
        self, key: str, expires_s: int = PRESIGN_SECONDS, *, download_name: str | None = None
    ) -> str: ...


@dataclass(frozen=True)
class S3Settings:
    """S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION."""

    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = DEFAULT_S3_REGION

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> S3Settings:
        return cls(
            endpoint=env_required("S3_ENDPOINT", env),
            bucket=env_required("S3_BUCKET", env),
            access_key=env_required("S3_ACCESS_KEY", env),
            secret_key=env_required("S3_SECRET_KEY", env),
            region=env_optional("S3_REGION", env) or DEFAULT_S3_REGION,
        )


class S3Storage:
    """`Storage` over boto3; `client` replaces the boto3 client in tests."""

    def __init__(self, settings: S3Settings, client: Any | None = None) -> None:
        if client is None:
            import boto3
            from botocore.config import Config

            # SigV4 for presigned URLs too: boto3 still presigns with the
            # legacy SigV2 query form unless told otherwise.
            client = boto3.client(
                "s3",
                endpoint_url=settings.endpoint,
                aws_access_key_id=settings.access_key,
                aws_secret_access_key=settings.secret_key,
                region_name=settings.region,
                config=Config(signature_version="s3v4"),
            )
        self._client = client
        self._bucket = settings.bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:  # boto raises many unrelated classes
            raise StorageError(f"upload failed: {exc}") from exc

    def get(self, key: str) -> bytes:
        try:
            body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError(f"download failed: {exc}") from exc
        return body

    def exists(self, key: str) -> bool:
        """Whether `key` is stored. Only a missing key is `False`; any other
        failure raises, so a broken bucket never reads as "not there yet"
        to a caller that would then pay to regenerate the object."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in MISSING_KEY_CODES:
                return False
            raise StorageError(f"head failed: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"head failed: {exc}") from exc
        return True

    def delete(self, *keys: str) -> None:
        """Delete one or more keys, 1000 per request (the S3 limit); missing keys are no error.

        `delete_objects` answers 200 even when single keys fail and lists
        them under `Errors` (`Quiet` only drops the `Deleted` list). Every
        batch is sent, then a `StorageError` names the failed keys and
        their codes, so a caller never takes a refused delete for done.
        """
        failed: list[str] = []
        try:
            for start in range(0, len(keys), 1000):
                batch = keys[start : start + 1000]
                response = self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
                )
                for error in (response or {}).get("Errors", []):
                    if error.get("Code") not in MISSING_KEY_CODES:
                        failed.append(f"{error.get('Key')} ({error.get('Code')})")
        except Exception as exc:
            raise StorageError(f"delete failed: {exc}") from exc
        if failed:
            shown = ", ".join(failed[:10]) + (
                f" and {len(failed) - 10} more" if len(failed) > 10 else ""
            )
            raise StorageError(f"delete failed for {len(failed)} of {len(keys)} keys: {shown}")

    def presigned_get(
        self, key: str, expires_s: int = PRESIGN_SECONDS, *, download_name: str | None = None
    ) -> str:
        """A URL that fetches `key` without credentials until `expires_s` seconds pass.

        With `download_name` the response is an attachment saved under that
        name (`attachment_disposition`); without it, the object is served
        as stored, for inline use.
        """
        if not 0 < expires_s <= PRESIGN_MAX_SECONDS:
            raise ValueError(f"expires_s must be between 1 and {PRESIGN_MAX_SECONDS}")
        params = {"Bucket": self._bucket, "Key": key}
        if download_name is not None:
            params["ResponseContentDisposition"] = attachment_disposition(download_name)
        try:
            url: str = self._client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_s
            )
        except Exception as exc:
            raise StorageError(f"presign failed: {exc}") from exc
        return url


def attachment_disposition(name: str) -> str:
    """`attachment; filename="<ascii>"; filename*=UTF-8''<encoded>` (RFC 6266).

    `filename*` carries the name exactly, umlauts included; `filename` is
    the fallback for a client that ignores it, character by character:
    accents stripped, anything else outside printable ASCII, `"` and `\\`
    replaced by `_`.
    A name that is empty or holds a control character (which would
    break the header) is a `ValueError`.
    """
    if not name or any(unicodedata.category(c) == "Cc" for c in name):
        raise ValueError("download name must be non-empty and free of control characters")
    fallback = "".join(_ascii_fallback(c) for c in name)
    encoded = quote(name, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def _ascii_fallback(char: str) -> str:
    """`ä` -> `a`; a character without an ASCII base, `"` or `\\` -> `_`."""
    folded = unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode()
    if not folded or not folded.isprintable() or folded in ('"', "\\"):
        return "_"
    return folded


def object_key(notebook_id: Any, owner_id: Any, name: str) -> str:
    """`<notebook_id>/<output_id>/<name>`, or `<user_id>/<library_source_id>/<name>`
    for an upload (the first argument is then the user).

    Both ids must be UUIDs and `name` one plain path segment (no `/` or
    `\\`, not `.` or `..`, no control characters, at most 255 characters),
    so a key can never reach outside its owner's prefix, whatever the
    caller passed; `ValueError` otherwise.
    """
    ids = []
    for value in (notebook_id, owner_id):
        try:
            ids.append(str(UUID(str(value))))
        except ValueError as exc:
            raise ValueError(f"object key ids must be UUIDs, got {value!r}") from exc
    if (
        not name
        or len(name) > 255
        or name in {".", ".."}
        or any(ch in name for ch in "/\\")
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
    ):
        raise ValueError(f"object name must be one plain path segment, got {name!r}")
    return f"{ids[0]}/{ids[1]}/{name}"
