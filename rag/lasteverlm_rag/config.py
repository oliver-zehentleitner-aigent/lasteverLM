"""Configuration from the environment. The shared parts (auth, inference, prices)
are loaded by core; this module adds what only rag needs. Startup fails on the
first missing or invalid value and on a configured model without a price."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from lasteverlm_core import (
    DEFAULT_TTS_VOICE,
    AuthSettings,
    ConfigError,
    InferenceSettings,
    ModelPrices,
    RateLimitSettings,
    S3Settings,
    env_int,
    env_optional,
    env_required,
    load_model_prices,
    require_prices,
)

from .options import is_voice


@dataclass(frozen=True)
class Settings:
    database_url: str
    auth: AuthSettings
    inference: InferenceSettings
    rate_limit: RateLimitSettings
    model_prices: ModelPrices
    tts_model: str | None
    tts_voice: str
    s3: S3Settings | None
    retrieval_k: int
    retrieval_generated_slots: int
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
            [
                inference.llm_model,
                inference.embedding_model,
                inference.decision_model,
                *([tts_model] if tts_model else []),
            ],
        )
        retrieval_k = env_int("RETRIEVAL_K", 8, env)
        if retrieval_k <= 0:
            raise ConfigError(f"RETRIEVAL_K must be positive, got {retrieval_k}")
        generated_slots = env_int("RETRIEVAL_GENERATED_SLOTS", 2, env)
        if generated_slots < 0:
            raise ConfigError(
                f"RETRIEVAL_GENERATED_SLOTS must not be negative, got {generated_slots}"
            )
        return cls(
            database_url=env_required("DATABASE_URL", env),
            auth=AuthSettings.from_env(env),
            inference=inference,
            rate_limit=RateLimitSettings.from_env(env),
            model_prices=prices,
            tts_model=tts_model,
            tts_voice=_voice(env_optional("TTS_VOICE", env) or DEFAULT_TTS_VOICE),
            s3=_s3(env, tts_model),
            retrieval_k=retrieval_k,
            retrieval_generated_slots=generated_slots,
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


def _s3(env: Mapping[str, str], tts_model: str | None) -> S3Settings | None:
    """Object storage holds the audio files: required once audio is enabled,
    optional otherwise (an API without it cannot serve audio rows)."""
    if env_optional("S3_ENDPOINT", env) is None:
        if tts_model:
            raise ConfigError("TTS_MODEL is set but S3_ENDPOINT is not: audio needs object storage")
        return None
    return S3Settings.from_env(env)


def _voice(voice: str) -> str:
    if not is_voice(voice):
        raise ConfigError(f"TTS_VOICE {voice!r} is not one of the platform's voices")
    return voice
