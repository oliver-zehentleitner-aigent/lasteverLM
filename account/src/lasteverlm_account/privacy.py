"""Privacy by design for the visitor log: no raw IP is ever stored or logged.

A visitor is identified by ``sha256(daily_salt || ip)``. The salt is random,
lives only in process memory and is replaced when the UTC date changes, so the
same address hashes to the same value within one day (unique visitors per day are
countable) and to an unrelated value the next day (no cross-day tracking). The
salt is never persisted; after a restart the current day's hashes change, which
costs at most one day's unique-visitor count and is accepted on purpose.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, date, datetime


class DailySalt:
    def __init__(self) -> None:
        self._day: date | None = None
        self._salt: bytes = b""

    def for_day(self, day: date) -> bytes:
        if day != self._day:
            self._day = day
            self._salt = secrets.token_bytes(32)
        return self._salt


def visitor_hash(ip: str, salt: bytes) -> str:
    return hashlib.sha256(salt + ip.strip().encode()).hexdigest()[:32]


def client_ip(
    client_host: str | None, forwarded_for: str | None, *, trust_proxy_headers: bool
) -> str:
    """The caller's address: first hop of X-Forwarded-For behind the ingress, else the peer."""
    if trust_proxy_headers and forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return client_host or "unknown"


_UA_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bot", re.compile(r"bot|crawl|spider|slurp|curl|wget|python-requests|httpx", re.I)),
    ("edge", re.compile(r"Edg/", re.I)),
    ("opera", re.compile(r"OPR/|Opera", re.I)),
    ("samsung", re.compile(r"SamsungBrowser", re.I)),
    ("chrome", re.compile(r"Chrome/|CriOS/", re.I)),
    ("firefox", re.compile(r"Firefox/|FxiOS/", re.I)),
    ("safari", re.compile(r"Safari/", re.I)),
)


def ua_family(user_agent: str | None) -> str:
    """Browser family only. The full user agent string is a fingerprint and is not kept."""
    if not user_agent:
        return "unknown"
    for name, pattern in _UA_FAMILIES:
        if pattern.search(user_agent):
            return name
    return "other"


def utc_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(UTC).date()
