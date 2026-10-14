"""Vultr's billing API, read with VULTR_BILLING_API_KEY (context/finance.md): the running
month's pending charges and the items of the latest invoices, as monthly cost lines in USD.
Field names and paths as in Vultr's official Go client (govultr, billing.go).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

VULTR_API = "https://api.vultr.com"
INVOICES_FETCHED = 3  # closed months to re-read on every sync; older ones do not change


@dataclass(frozen=True)
class CostLine:
    month: date  # first day of the month the charge belongs to
    item: str
    amount_cents: int
    currency: str = "USD"


class VultrError(Exception):
    """The billing API refused or failed; the message never contains the key."""


class VultrBilling:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = VULTR_API,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout_seconds

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            r = await client.get(f"{self._base}{path}", headers=self._headers)
        except httpx.HTTPError as exc:
            raise VultrError(f"{path}: unreachable ({type(exc).__name__})") from exc
        if not r.is_success:
            raise VultrError(f"{path}: HTTP {r.status_code}")
        return r.json()

    async def cost_lines(self) -> list[CostLine]:
        """Pending charges plus the items of the last invoices, summed per month and item."""
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            items = list(
                (await self._get(client, "/v2/billing/pending-charges")).get("pending_charges", [])
            )
            invoices = (
                await self._get(client, f"/v2/billing/invoices?per_page={INVOICES_FETCHED}")
            ).get("billing_invoices", [])
            for invoice in invoices[:INVOICES_FETCHED]:
                body = await self._get(
                    client, f"/v2/billing/invoices/{invoice['id']}/items?per_page=500"
                )
                items.extend(body.get("invoice_items", []))
        return summarize(items)


def summarize(items: list[dict[str, Any]]) -> list[CostLine]:
    totals: dict[tuple[date, str], float] = defaultdict(float)
    for it in items:
        start = str(it.get("start_date") or "")[:10]
        if len(start) != 10:
            continue
        day = date.fromisoformat(start)
        name = str(it.get("description") or it.get("product") or "unnamed")[:200]
        totals[(day.replace(day=1), name)] += float(it.get("total") or 0)
    return [
        CostLine(month, item, round(total * 100))
        for (month, item), total in sorted(totals.items())
        if total > 0
    ]
