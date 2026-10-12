"""Object storage for uploaded files, behind one interface.

The implementation is an S3 client (boto3) pointed at Vultr Object
Storage. Object keys follow the family contract:
`<notebook_id>/<source_id>/<name>`.
"""

from __future__ import annotations

from typing import Any, Protocol


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, keys: list[str]) -> None: ...


class S3Storage:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        client: Any | None = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:  # boto raises many unrelated classes
            raise StorageError(f"upload failed: {exc}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError(f"download failed: {exc}") from exc

    def delete(self, keys: list[str]) -> None:
        if not keys:
            return
        try:
            for start in range(0, len(keys), 1000):
                batch = keys[start : start + 1000]
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
                )
        except Exception as exc:
            raise StorageError(f"delete failed: {exc}") from exc


def object_key(notebook_id: Any, source_id: Any, name: str) -> str:
    return f"{notebook_id}/{source_id}/{name}"
