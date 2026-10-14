"""Calls into the other services on an admin's behalf: today only the purge of a user's data
in rag and ingest, which account orchestrates because a user's data lives in three
services (context/deletion.md). The admin's bearer is forwarded; each step is one request.
"""

from __future__ import annotations

import uuid
from typing import Literal

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
