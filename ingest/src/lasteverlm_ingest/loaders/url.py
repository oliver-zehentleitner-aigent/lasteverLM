"""Web pages and documents behind a URL.

The stored object of a `url` source is the URL itself; the worker
fetches it here, so the API pods never open a connection to an address a
user chose. Every connection, including each redirect hop, goes through
`GuardedBackend`, which resolves the host itself and refuses any address
that is not public: the worker runs inside the cluster, next to the
database, the cloud metadata endpoint and the other services.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore

from lasteverlm_ingest.loaders import LoaderError, Passage, SourceLoader, TransientLoaderError
from lasteverlm_ingest.loaders.html import HtmlLoader

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
AddressCheck = Callable[[IPAddress], bool]
Resolve = Callable[..., list[Any]]

MAX_REDIRECTS = 5
# getaddrinfo has no timeout of its own; lookups run here so the fetch
# deadline bounds them. A lookup that never returns keeps its thread, so
# the pool is small and a full pool makes the next lookups time out too.
_RESOLVER = ThreadPoolExecutor(max_workers=4, thread_name_prefix="url-resolve")
USER_AGENT = "lasteverLM-ingest/0.1 (+https://github.com/oliver-zehentleitner/lasteverLM)"
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_TYPES = frozenset({"text/plain", "text/markdown"})
_PDF_TYPES = frozenset({"application/pdf"})


def is_public(address: IPAddress) -> bool:
    """True only for globally routable unicast addresses."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast and not address.is_reserved


def check_url(url: str) -> str:
    """Syntax check shared by the API and the loader: absolute http(s)
    with a host and without credentials. Raises ValueError."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parts.hostname:
        raise ValueError("URL has no host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL must not contain credentials")
    try:
        _ = parts.port
    except ValueError:
        raise ValueError("URL has an invalid port") from None
    return parts.geturl()


def normalize_url(url: str) -> str:
    """The form two URLs are compared in for the library: scheme and host
    lowercased, a default port and the fragment dropped, an empty path as
    `/`; path and query are kept as they are."""
    parts = urlsplit(check_url(url))
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and (parts.scheme, port) not in (("http", 80), ("https", 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


class BlockedAddressError(LoaderError):
    pass


class GuardedBackend(httpcore.NetworkBackend):
    """Resolves the host, refuses it if any of its addresses fails
    `allowed`, and connects to an address it checked: a second DNS
    answer (rebinding) never reaches the socket."""

    def __init__(
        self, allowed: AddressCheck = is_public, resolve: Resolve = socket.getaddrinfo
    ) -> None:
        self._allowed = allowed
        self._resolve = resolve
        self._inner = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        lookup = _RESOLVER.submit(self._resolve, host, port, type=socket.SOCK_STREAM)
        try:
            infos = lookup.result(timeout=timeout)
        except TimeoutError:
            lookup.cancel()
            raise TransientLoaderError(f"host {host!r} did not resolve in time") from None
        except socket.gaierror as exc:
            raise LoaderError(f"host {host!r} could not be resolved") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        if not addresses or not all(self._allowed(a) for a in addresses):
            raise BlockedAddressError(f"host {host!r} is not a public address")
        return self._inner.connect_tcp(
            str(addresses[0]), port, timeout, local_address, socket_options
        )

    def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.NetworkStream:
        raise BlockedAddressError("unix sockets are not fetched")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


@dataclass(frozen=True)
class Fetched:
    url: str
    media_type: str
    charset: str | None
    body: bytes


class Fetcher:
    """GET with manual redirects, a byte cap and an overall deadline.

    4xx answers, a blocked address, an unsupported type or a body over
    the cap are permanent (`LoaderError`); timeouts, connection errors,
    429 and 5xx may pass later (`TransientLoaderError`)."""

    def __init__(
        self,
        *,
        max_bytes: int,
        timeout_seconds: float = 30.0,
        allowed: AddressCheck = is_public,
    ) -> None:
        self._max_bytes = max_bytes
        self._timeout = timeout_seconds
        self._pool = httpcore.ConnectionPool(network_backend=GuardedBackend(allowed), retries=0)

    def fetch(self, url: str) -> Fetched:
        deadline = time.monotonic() + self._timeout
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                current = check_url(current)
            except ValueError as exc:
                raise LoaderError(str(exc)) from None
            result = self._get(current, deadline)
            if isinstance(result, Fetched):
                return result
            current = urljoin(current, result)
        raise LoaderError(f"more than {MAX_REDIRECTS} redirects")

    def _get(self, url: str, deadline: float) -> Fetched | str:
        remaining = max(0.1, deadline - time.monotonic())
        extensions = {
            "timeout": {
                "connect": remaining,
                "read": remaining,
                "write": remaining,
                "pool": remaining,
            }
        }
        headers = [
            (b"User-Agent", USER_AGENT.encode()),
            (b"Accept", b"text/html,text/plain,application/pdf;q=0.9,*/*;q=0.1"),
        ]
        try:
            with self._pool.stream("GET", url, headers=headers, extensions=extensions) as response:
                status = response.status
                fields = {
                    k.decode("latin-1").lower(): v.decode("latin-1") for k, v in response.headers
                }
                if status in (301, 302, 303, 307, 308):
                    location = fields.get("location")
                    if not location:
                        raise LoaderError(f"redirect {status} without a location")
                    return location
                if status == 429 or status >= 500:
                    raise TransientLoaderError(f"{url} answered {status}")
                if status >= 400:
                    raise LoaderError(f"{url} answered {status}")
                if status != 200:
                    raise LoaderError(f"{url} answered {status}, expected 200")
                media_type, charset = _content_type(fields.get("content-type", ""))
                if media_type not in _HTML_TYPES | _TEXT_TYPES | _PDF_TYPES:
                    raise LoaderError(f"unsupported content type {media_type or 'none'!r}")
                body = bytearray()
                for piece in response.iter_stream():
                    body.extend(piece)
                    if len(body) > self._max_bytes:
                        raise LoaderError("page is too large")
                    if time.monotonic() > deadline:
                        raise TransientLoaderError(f"{url} took too long to load")
        except httpcore.TimeoutException as exc:
            raise TransientLoaderError(f"{url} took too long to load") from exc
        except (httpcore.ConnectError, httpcore.ReadError, httpcore.RemoteProtocolError) as exc:
            raise TransientLoaderError(f"{url} could not be loaded: {exc}") from exc
        except httpcore.UnsupportedProtocol as exc:
            raise LoaderError(str(exc)) from exc
        return Fetched(url=url, media_type=media_type, charset=charset, body=bytes(body))


def _content_type(value: str) -> tuple[str, str | None]:
    media_type, _, params = value.partition(";")
    charset = None
    for param in params.split(";"):
        key, _, val = param.partition("=")
        if key.strip().lower() == "charset":
            charset = val.strip().strip('"') or None
    return media_type.strip().lower(), charset


class UrlLoader:
    """Loads the URL stored as the source's object and hands the body to
    the loader for its content type: HTML pages, plain text, PDF."""

    def __init__(
        self,
        *,
        fetch: Callable[[str], Fetched],
        text: SourceLoader,
        pdf: SourceLoader,
        html: HtmlLoader | None = None,
    ) -> None:
        self._fetch = fetch
        self._text = text
        self._pdf = pdf
        self._html = html or HtmlLoader()

    def load(self, data: bytes) -> list[Passage]:
        return self.load_page(data)[1]

    def load_page(self, data: bytes) -> tuple[Fetched, list[Passage]]:
        """The fetch itself (final URL, type, body) and what was read from
        it; the worker keeps a snapshot of the former."""
        fetched = self._fetch(data.decode("utf-8").strip())
        if fetched.media_type in _HTML_TYPES:
            return fetched, self._html.load(fetched.body, fetched.charset)
        if fetched.media_type in _PDF_TYPES:
            return fetched, self._pdf.load(fetched.body)
        return fetched, self._text.load(fetched.body)
