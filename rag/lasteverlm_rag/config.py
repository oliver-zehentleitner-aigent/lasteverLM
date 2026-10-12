"""Configuration from the environment. Fails at startup when a required value is missing
or when a configured model has no price (every call must be accountable)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from .contracts import ModelPrice, parse_model_prices


class ConfigError(RuntimeError):
    """A required environment variable is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    inference_base_url: str
    inference_api_key: str
    llm_model: str
    embedding_model: str
    embedding_dimension: int
    tts_model: str | None
    auth_jwt_secret: str | None
    demo_token: str | None
    model_prices: dict[str, ModelPrice]
    retrieval_k: int
    similarity_floor: float
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"missing required environment variable {name}")
            return value

        jwt_secret = env.get("AUTH_JWT_SECRET", "").strip() or None
        demo_token = env.get("DEMO_TOKEN", "").strip() or None
        if not jwt_secret and not demo_token:
            raise ConfigError("set AUTH_JWT_SECRET or DEMO_TOKEN (one of them is required)")

        llm_model = required("LLM_MODEL")
        embedding_model = required("EMBEDDING_MODEL")
        tts_model = env.get("TTS_MODEL", "").strip() or None
        prices = _model_prices(env.get("MODEL_PRICES", ""))
        for model in (llm_model, embedding_model, *([tts_model] if tts_model else [])):
            if model not in prices:
                raise ConfigError(f"MODEL_PRICES has no price for configured model {model!r}")

        return cls(
            database_url=required("DATABASE_URL"),
            inference_base_url=required("INFERENCE_BASE_URL").rstrip("/"),
            inference_api_key=required("INFERENCE_API_KEY"),
            llm_model=llm_model,
            embedding_model=embedding_model,
            embedding_dimension=_positive_int(
                env.get("EMBEDDING_DIMENSION", "1536"), "EMBEDDING_DIMENSION"
            ),
            tts_model=tts_model,
            auth_jwt_secret=jwt_secret,
            demo_token=demo_token,
            model_prices=prices,
            retrieval_k=_positive_int(env.get("RETRIEVAL_K", "8"), "RETRIEVAL_K"),
            similarity_floor=_unit_float(env.get("SIMILARITY_FLOOR", "0.3"), "SIMILARITY_FLOOR"),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
        )


def _model_prices(raw: str) -> dict[str, ModelPrice]:
    try:
        return parse_model_prices(raw)
    except (ValueError, TypeError, ValidationError) as exc:
        raise ConfigError(
            'MODEL_PRICES must be JSON {"<model>": {"in": cents, "out": cents}}: ' + str(exc)
        ) from exc


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


def _unit_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{name} must be between 0 and 1, got {value}")
    return value
