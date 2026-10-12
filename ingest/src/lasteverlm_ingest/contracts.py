"""Mirror of the models and helpers that `lasteverlm-core` will export.

The family's shared library is not published yet. Everything in this
module is a local copy of what core defines (or will define) and is
replaced by `from lasteverlm_core import ...` once core is available;
nothing here is this service's own design. Keep it free of ingest-specific
logic so the swap is a pure import change.
"""

from __future__ import annotations

import hmac
import json
import math
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field

# The user id every request carries when the deployment runs with a shared
# demo token instead of real logins. Fixed so that all services agree on
# which rows belong to the demo user.
DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")

# `url` and `image` are later loaders; `generated` is a finished output the
# rag service indexed as a source — ingest lists and deletes it, never
# loads it.
SourceKind = Literal["pdf", "text", "url", "image", "generated"]
SourceStatus = Literal["processing", "ready", "failed"]


class Notebook(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime


class NotebookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Source(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notebook_id: UUID
    name: str
    kind: SourceKind
    status: SourceStatus
    error: str | None = None
    created_at: datetime


class SourceFromUrl(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class UsageRecord(BaseModel):
    """One row of the shared `usage` table; the account service sums it."""

    user_id: UUID
    notebook_id: UUID | None
    service: str
    kind: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_cents: int


class ModelPrice(BaseModel):
    """Cents per million tokens; wire names are "in" and "out"."""

    model_config = ConfigDict(populate_by_name=True)

    cents_in: float = Field(alias="in", ge=0)
    cents_out: float = Field(alias="out", ge=0)


ModelPrices = dict[str, ModelPrice]

# Core carries the defaults for the family's models; a deployment overrides
# them with the MODEL_PRICES environment variable (same JSON shape).
DEFAULT_MODEL_PRICES: ModelPrices = {}


class UnpricedModelError(ValueError):
    """A model call would not be accounted — refused, never billed at zero."""


def parse_model_prices(raw: str | None) -> ModelPrices:
    prices = dict(DEFAULT_MODEL_PRICES)
    if raw and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MODEL_PRICES is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("MODEL_PRICES must be a JSON object keyed by model name")
        for model, entry in parsed.items():
            try:
                prices[model] = ModelPrice.model_validate(entry)
            except ValueError as exc:
                raise ValueError(f"MODEL_PRICES[{model!r}] needs numeric 'in' and 'out'") from exc
    return prices


def require_prices(prices: ModelPrices, models: list[str]) -> None:
    """Fail loud at startup: every configured model must be priced."""
    missing = [m for m in models if m not in prices]
    if missing:
        raise UnpricedModelError(
            f"no price in MODEL_PRICES for {', '.join(repr(m) for m in missing)}; "
            "every model call must be accounted"
        )


def cost_cents(prices: ModelPrices, model: str, tokens_in: int, tokens_out: int) -> int:
    """`ceil((tokens_in * in + tokens_out * out) / 1e6)`. An unpriced model
    raises rather than costing zero."""
    price = prices.get(model)
    if price is None:
        raise UnpricedModelError(f"model {model!r} has no price")
    cents = (tokens_in * price.cents_in + tokens_out * price.cents_out) / 1_000_000
    return math.ceil(cents) if cents > 0 else 0


_BALANCE_SQL = """
select coalesce((select sum(amount_cents) from ledger where user_id = %(user)s), 0)
     - coalesce((select sum(cost_cents) from usage where user_id = %(user)s), 0)
"""

_USAGE_SQL = """
insert into usage (user_id, notebook_id, service, kind, model, tokens_in, tokens_out, cost_cents)
values (%(user_id)s, %(notebook_id)s, %(service)s, %(kind)s, %(model)s,
        %(tokens_in)s, %(tokens_out)s, %(cost_cents)s)
"""


def balance_cents(conn: Any, user_id: UUID) -> int:
    """Credits minus usage, both from the shared tables. Usage rows are the
    only debit; there is no second ledger write."""
    with conn.cursor() as cur:
        cur.execute(_BALANCE_SQL, {"user": user_id})
        row = cur.fetchone()
    return int(row[0]) if row else 0


def record_usage(
    conn: Any,
    user_id: UUID,
    notebook_id: UUID | None,
    service: str,
    kind: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    *,
    prices: ModelPrices,
) -> UsageRecord:
    usage = UsageRecord(
        user_id=user_id,
        notebook_id=notebook_id,
        service=service,
        kind=kind,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_cents=cost_cents(prices, model, tokens_in, tokens_out),
    )
    with conn.cursor() as cur:
        cur.execute(_USAGE_SQL, usage.model_dump())
    return usage


class AuthError(Exception):
    """The bearer token is missing, malformed, expired or wrong."""


JWT_ISSUER = "lasteverlm"


def verify_token(token: str, *, jwt_secret: str | None, demo_token: str | None) -> UUID:
    """Return the user id a bearer token stands for, or raise AuthError.

    Both schemes may be configured at once. A JWT (HS256, issuer
    `lasteverlm`, user id in `sub`, as the account service issues it) is
    checked first when a secret is set; then the demo token, in constant
    time, when one is set.
    """
    if jwt_secret is not None:
        try:
            claims = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                options={"require": ["sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            jwt_error: str | None = f"invalid token: {exc}"
        else:
            try:
                return UUID(str(claims["sub"]))
            except ValueError as exc:
                raise AuthError("token subject is not a user id") from exc
    else:
        jwt_error = None
    if demo_token is not None:
        if hmac.compare_digest(token.encode(), demo_token.encode()):
            return DEMO_USER_ID
        raise AuthError(jwt_error or "invalid token")
    raise AuthError(jwt_error or "no authentication scheme configured")
