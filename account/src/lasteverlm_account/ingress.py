"""Is the public entrance up: the same request a browser makes, from inside the cluster
through the load balancer, and the certificate it is served with (context/system.md)."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx

CertFetcher = Callable[[str, int], Awaitable[datetime]]


@dataclass(frozen=True)
class IngressStatus:
    status: str  # "ok" | "down"
    url: str
    tls_expires_at: datetime | None
    checked_at: datetime
    error: str | None


async def tls_not_after(host: str, port: int, timeout: float = 3.0) -> datetime:
    """The served certificate's notAfter, from a verified TLS handshake (SNI = host)."""
    context = ssl.create_default_context()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=context, server_hostname=host), timeout
    )
    try:
        cert = writer.get_extra_info("ssl_object").getpeercert()
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), tz=UTC)
    finally:
        writer.close()
        _ = reader


class IngressProbe:
    """GET <PUBLIC_BASE_URL>/api/account/healthz (3 s), the certificate's expiry; cached 60 s."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        cert: CertFetcher = tls_not_after,
        timeout_seconds: float = 3.0,
        ttl: timedelta = timedelta(seconds=60),
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/api/account/healthz"
        self._transport = transport
        self._cert = cert
        self._timeout = timeout_seconds
        self._ttl = ttl
        self._cached: IngressStatus | None = None

    async def status(self, now: datetime) -> IngressStatus:
        if self._cached is not None and now - self._cached.checked_at < self._ttl:
            return self._cached
        parts = urlsplit(self.url)
        error: str | None = None
        expires: datetime | None = None
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as client:
                r = await client.get(self.url)
            if r.status_code != 200:
                error = f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        if parts.scheme == "https" and parts.hostname:
            try:
                expires = await self._cert(parts.hostname, parts.port or 443)
            except (OSError, ssl.SSLError, TimeoutError, ValueError, KeyError) as exc:
                error = error or f"TLS: {type(exc).__name__}: {exc}"[:300]
        self._cached = IngressStatus("down" if error else "ok", self.url, expires, now, error)
        return self._cached
