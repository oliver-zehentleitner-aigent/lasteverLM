"""Calls into the other services on an admin's behalf: today only the purge of a user's data
in rag and ingest, which account orchestrates because a user's data lives in three
services (context/deletion.md). The admin's bearer is forwarded; each step is one request.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

import httpx

PurgeStep = Literal["rag", "ingest"]


class PurgeError(Exception):
    """A service could not purge the user; `step` names it, the message is the service's."""

    def __init__(self, step: PurgeStep, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message


class ServiceClient:
    def __init__(
        self,
        *,
        ingest_url: str,
        rag_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._urls = {"ingest": ingest_url.rstrip("/"), "rag": rag_url.rstrip("/")}
        self._transport = transport
        self._timeout = timeout_seconds

    def purge_url(self, step: PurgeStep, user_id: uuid.UUID) -> str:
        return f"{self._urls[step]}/api/{step}/admin/users/{user_id}"

    async def purge_user(self, step: PurgeStep, user_id: uuid.UUID, bearer: str) -> None:
        """DELETE the user's data in one service; 2xx is done (idempotent on their side)."""
        url = self.purge_url(step, user_id)
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as client:
                r = await client.delete(url, headers={"Authorization": bearer})
        except httpx.HTTPError as exc:
            raise PurgeError(step, f"unreachable ({type(exc).__name__})") from exc
        if r.is_success:
            return
        detail = ""
        try:
            body = r.json()
            detail = str(body.get("error", "")) if isinstance(body, dict) else ""
        except ValueError:
            detail = ""
        raise PurgeError(step, f"HTTP {r.status_code}" + (f" {detail}" if detail else ""))


class EstimateError(Exception):
    """An estimate could not be had; the price list leaves that price empty."""


async def _json(client: httpx.AsyncClient, method: str, url: str, **kw: Any) -> dict[str, Any]:
    try:
        r = await client.request(method, url, **kw)
    except httpx.HTTPError as exc:
        raise EstimateError(f"{url}: unreachable ({type(exc).__name__})") from exc
    if not r.is_success:
        raise EstimateError(f"{url}: HTTP {r.status_code}")
    try:
        body = r.json()
    except ValueError as exc:
        raise EstimateError(f"{url}: not JSON") from exc
    if not isinstance(body, dict):
        raise EstimateError(f"{url}: not an object")
    return body


class EstimateClient:
    """Price estimates of rag (outputs, chat, judge) and ingest (sources), for the public
    price list. Only the charge fields are read; costs never leave this module."""

    def __init__(
        self,
        *,
        ingest_url: str,
        rag_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._ingest = ingest_url.rstrip("/")
        self._rag = rag_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout)

    async def rag(self, body: dict[str, Any], bearer: str) -> tuple[Decimal, Decimal]:
        """(min, max) charge in euro cents of one output or action with default options."""
        async with self._client() as client:
            data = await _json(
                client,
                "POST",
                f"{self._rag}/api/rag/estimate",
                json=body,
                headers={"Authorization": bearer},
            )
        try:
            return Decimal(str(data["charge_cents_min"])), Decimal(str(data["charge_cents_max"]))
        except (KeyError, ArithmeticError) as exc:
            raise EstimateError("rag estimate without charge_cents_min/max") from exc

    async def ingest(self, kind: str, bearer: str) -> tuple[Decimal, Decimal]:
        """(per unit, per source) charge in euro cents of a source kind: one nominal unit
        (margin only), and what each source adds once (summary at its largest, fee)."""
        async with self._client() as client:
            data = await _json(
                client,
                "GET",
                f"{self._ingest}/api/ingest/estimate",
                params={"kind": kind},
                headers={"Authorization": bearer},
            )
        try:
            return (
                Decimal(str(data["charge_cents"])),
                Decimal(str(data.get("per_source_charge_cents") or 0)),
            )
        except (KeyError, ArithmeticError) as exc:
            raise EstimateError("ingest estimate without charge_cents") from exc
