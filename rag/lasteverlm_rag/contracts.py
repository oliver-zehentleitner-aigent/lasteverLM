"""Shared contract types, mirrored from the upcoming ``lasteverlm_core`` library.

Temporary: once ``lasteverlm-core`` is published this module is replaced by
``from lasteverlm_core import ...`` and deleted. Keep it free of anything
service-specific so the swap is mechanical. Shapes follow the parent's
docs/architecture.md v1.
"""

from __future__ import annotations

import hmac
import json
import math
from collections.abc import Mapping
from typing import Any, Literal

import jwt
from pydantic import BaseModel, Field

# Owner id of every notebook created under the shared demo token; pinned in lasteverlm_core.
DEMO_USER_ID = "00000000-0000-4000-8000-000000000001"

SourceKind = Literal["pdf", "text", "url", "image", "generated"]
OutputKind = Literal["report", "quiz", "table", "mindmap", "infographic", "audio"]
OutputStatus = Literal["waiting", "processing", "ready", "failed"]
OUTPUT_KINDS: tuple[OutputKind, ...] = (
    "report",
    "quiz",
    "table",
    "mindmap",
    "infographic",
    "audio",
)


class AuthError(Exception):
    """The request carries no valid credential."""


def verify_token(token: str, jwt_secret: str | None, demo_token: str | None) -> str:
    """Return the user id for a bearer token, or raise AuthError.

    A JWT (HS256, ``sub`` is the user id) is tried first when a secret is
    configured, the shared demo token second when one is configured.
    """
    if not token:
        raise AuthError("missing bearer token")
    if jwt_secret:
        try:
            claims = jwt.decode(token, jwt_secret, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            claims = None
        if claims is not None:
            sub = claims.get("sub")
            if not sub:
                raise AuthError("token has no subject")
            return str(sub)
    if demo_token and hmac.compare_digest(token, demo_token):
        return DEMO_USER_ID
    raise AuthError("invalid bearer token")


class Citation(BaseModel):
    n: int
    source_id: str
    source_name: str
    source_kind: SourceKind
    chunk_id: str
    page: int | None = None
    quote: str


class AskScope(BaseModel):
    output_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    scope: AskScope | None = None


class Answer(BaseModel):
    message_id: str
    answer: str
    citations: list[Citation]


class Message(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]] | None = None
    created_at: str


class OutputCreate(BaseModel):
    kind: OutputKind


class Output(BaseModel):
    id: str
    notebook_id: str
    kind: OutputKind
    title: str
    content: dict[str, Any] | None = None
    status: OutputStatus
    error: str | None = None
    share_token: str | None = None
    source_id: str | None = None
    created_at: str


class SharedOutput(BaseModel):
    """What ``GET /shared/{token}`` returns: the document without any ids."""

    kind: OutputKind
    title: str
    content: dict[str, Any] | None = None
    created_at: str


class ModelPrice(BaseModel):
    """Cents per million tokens, input and output."""

    cents_in: float = Field(alias="in", ge=0)
    cents_out: float = Field(alias="out", ge=0)


def parse_model_prices(raw: str) -> dict[str, ModelPrice]:
    """Parse ``MODEL_PRICES``: JSON ``{"<model>": {"in": cents, "out": cents}}``."""
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object keyed by model name")
    return {model: ModelPrice.model_validate(price) for model, price in data.items()}


def cost_cents(
    model: str, tokens_in: int, tokens_out: int, prices: Mapping[str, ModelPrice]
) -> int:
    """Price a call at write time: ``ceil((tokens_in * in + tokens_out * out) / 1e6)``."""
    price = prices[model]
    return math.ceil((tokens_in * price.cents_in + tokens_out * price.cents_out) / 1_000_000)
