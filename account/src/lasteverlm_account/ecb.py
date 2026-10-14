"""The ECB's daily euro reference rates (context/finance.md): the USD rate is US dollars per
euro, exactly the pricing rules' ``usd_per_eur``. Published once per working day.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_NS = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}"


class EcbError(Exception):
    """The reference rates could not be read; the message says why."""


class EcbRates:
    def __init__(
        self,
        url: str = ECB_DAILY_URL,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._url = url
        self._transport = transport
        self._timeout = timeout_seconds

    async def usd_per_eur(self) -> tuple[date, Decimal]:
        """The latest published USD rate and the day it is for."""
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as client:
                r = await client.get(self._url)
        except httpx.HTTPError as exc:
            raise EcbError(f"unreachable ({type(exc).__name__})") from exc
        if not r.is_success:
            raise EcbError(f"HTTP {r.status_code}")
        return parse_usd(r.content)


def parse_usd(xml: bytes) -> tuple[date, Decimal]:
    try:
        root = ET.fromstring(
            xml
        )  # noqa: S314 - one public document, no DTD, expat refuses entities from outside
    except ET.ParseError as exc:
        raise EcbError(f"not the reference rate document ({exc})") from exc
    for day in root.iter(f"{_NS}Cube"):
        when = day.get("time")
        if not when:
            continue
        for cube in day:
            if cube.get("currency") == "USD":
                try:
                    rate = Decimal(cube.get("rate", ""))
                    return date.fromisoformat(when), rate
                except (InvalidOperation, ValueError) as exc:
                    raise EcbError(f"unreadable USD rate {cube.get('rate')!r}") from exc
    raise EcbError("no USD rate in the document")
