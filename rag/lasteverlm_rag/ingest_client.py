"""Ingest's API as the agent chat uses it, always with the user's own bearer
from the request that runs the step (rag stores no tokens)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

import httpx

INGEST_TIMEOUT_S = 10.0


class IngestError(Exception):
    """Ingest refused or failed a call; ``status`` is its HTTP status (0: unreachable)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Ingest(Protocol):
    def add_url(self, bearer: str, notebook_id: str, url: str) -> dict[str, Any]: ...

    def add_library(
        self, bearer: str, notebook_id: str, library_ids: list[str]
    ) -> dict[str, Any]: ...

    def library(self, bearer: str) -> list[dict[str, Any]]: ...

    def url_charge_cents(self, bearer: str) -> Decimal:
        """What adding one web page charges: the page plus the per-source part."""
        ...


class HttpIngest:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/") + "/api/ingest"
        self._client = client or httpx.Client(timeout=INGEST_TIMEOUT_S)

    def _call(self, method: str, path: str, bearer: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(
                method, self._base + path, headers={"Authorization": bearer}, **kwargs
            )
        except httpx.HTTPError as exc:
            raise IngestError(0, f"ingest is not reachable: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            try:
                message = str(response.json().get("error") or response.text)
            except ValueError:
                message = response.text
            raise IngestError(response.status_code, message[:300])
        return response.json()

    def add_url(self, bearer: str, notebook_id: str, url: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "POST", f"/notebooks/{notebook_id}/sources", bearer, json={"url": url}
        )
        return result

    def add_library(self, bearer: str, notebook_id: str, library_ids: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "POST",
            f"/notebooks/{notebook_id}/sources/bulk",
            bearer,
            json={"library_ids": library_ids},
        )
        return result

    def library(self, bearer: str) -> list[dict[str, Any]]:
        result = self._call("GET", "/library", bearer, params={"kind": "all"})
        return list(result) if isinstance(result, list) else list(result.get("items", []))

    def url_charge_cents(self, bearer: str) -> Decimal:
        result = self._call("GET", "/estimate", bearer, params={"kind": "url"})
        return Decimal(str(result["charge_cents"])) + Decimal(
            str(result.get("per_source_charge_cents", "0"))
        )
