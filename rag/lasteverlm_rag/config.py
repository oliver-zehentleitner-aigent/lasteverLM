"""Configuration from the environment. The shared parts (auth, inference, prices)
are loaded by core; this module adds what only rag needs. Startup fails on the
first missing or invalid value and on a configured model without a price."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from lasteverlm_core import (
    AuthSettings,
    ConfigError,
    InferenceSettings,
    ModelPrices,
    RateLimitSettings,
    env_int,
    env_optional,
    env_required,
    load_model_prices,
    require_prices,
)


@dataclass(frozen=True)
class Settings:
    database_url: str
    auth: AuthSettings
    inference: InferenceSettings
    rate_limit: RateLimitSettings
    model_prices: ModelPrices
    tts_model: str | None
    retrieval_k: int
    similarity_floor: float
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        inference = InferenceSettings.from_env(env)
        tts_model = env_optional("TTS_MODEL", env)
        prices = load_model_prices(env)
        require_prices(
            prices,
            [inference.llm_model, inference.embedding_model, *([tts_model] if tts_model else [])],
        )
        retrieval_k = env_int("RETRIEVAL_K", 8, env)
        if retrieval_k <= 0:
            raise ConfigError(f"RETRIEVAL_K must be positive, got {retrieval_k}")
        return cls(
            database_url=env_required("DATABASE_URL", env),
            auth=AuthSettings.from_env(env),
            inference=inference,
            rate_limit=RateLimitSettings.from_env(env),
            model_prices=prices,
            tts_model=tts_model,
            retrieval_k=retrieval_k,
            similarity_floor=_unit_float(env.get("SIMILARITY_FLOOR", "0.3"), "SIMILARITY_FLOOR"),
            log_level=(env_optional("LOG_LEVEL", env) or "INFO").upper(),
        )


def _unit_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{name} must be between 0 and 1, got {value}")
    return value
