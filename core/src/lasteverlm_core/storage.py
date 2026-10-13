"""Object storage for uploads and generated files, behind one interface.

The implementation is an S3 client (boto3) pointed at Vultr Object
Storage, one bucket for the whole family. Object keys follow the family
contract: `<notebook_id>/<source_id>/<name>` for an upload,
`<notebook_id>/<output_id>/<name>` for a file an output produces.

A presigned GET is how a browser fetches a private object without a
bearer header (an `<audio>` element cannot send one); the URL carries its
own expiry and needs no further call to storage.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from botocore.exceptions import ClientError

from .settings import env_optional, env_required

PRESIGN_SECONDS = 3600
DEFAULT_S3_REGION = "us-east-1"
# What S3 implementations answer a HEAD on a missing key with.
MISSING_KEY_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class StorageError(Exception):
    """An object-storage request failed."""


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, *keys: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def presigned_get(self, key: str, expires_s: int = PRESIGN_SECONDS) -> str: ...


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
        """Delete one or more keys, 1000 per request (the S3 limit); missing keys are no error."""
        try:
            for start in range(0, len(keys), 1000):
                batch = keys[start : start + 1000]
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
                )
        except Exception as exc:
            raise StorageError(f"delete failed: {exc}") from exc

    def presigned_get(self, key: str, expires_s: int = PRESIGN_SECONDS) -> str:
        """A URL that fetches `key` without credentials until `expires_s` seconds pass."""
        if expires_s <= 0:
            raise ValueError("expires_s must be positive")
        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_s,
            )
        except Exception as exc:
            raise StorageError(f"presign failed: {exc}") from exc
        return url


def object_key(notebook_id: Any, owner_id: Any, name: str) -> str:
    """`<notebook_id>/<source_id or output_id>/<name>`."""
    return f"{notebook_id}/{owner_id}/{name}"
