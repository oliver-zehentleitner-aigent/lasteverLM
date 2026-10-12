"""Settings, read from the environment once at startup.

What the services share (inference endpoint, auth, model prices, rate
limits) is loaded by core; the rest is this service's own. A missing or
invalid value is a startup failure naming the variable (`ConfigError`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from lasteverlm_core import (
    AuthSettings,
    InferenceSettings,
    ModelPrices,
    RateLimitSettings,
    UnpricedModelError,
    load_model_prices,
    require_prices,
)
from lasteverlm_core.settings import ConfigError, env_int, env_optional, env_required

__all__ = ["ConfigError", "Settings"]


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    inference: InferenceSettings
    auth: AuthSettings
    rate_limit: RateLimitSettings
    max_upload_bytes: int
    chunk_tokens: int
    chunk_overlap_tokens: int
    embed_batch_size: int
    summary_input_tokens: int
    summary_max_tokens: int
    worker_poll_seconds: float
    claim_timeout_seconds: int
    log_level: str
    model_prices: ModelPrices = field(default_factory=dict)
    service_name: Literal["ingest", "rag"] = "ingest"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        chunk_tokens = env_int("CHUNK_TOKENS", 800, env)
        overlap = env_int("CHUNK_OVERLAP_TOKENS", 100, env)
        if not 0 <= overlap < chunk_tokens:
            raise ConfigError("CHUNK_OVERLAP_TOKENS must be >= 0 and smaller than CHUNK_TOKENS")
        poll_seconds = env_int("WORKER_POLL_SECONDS", 2, env)
        claim_timeout = env_int("CLAIM_TIMEOUT_SECONDS", 600, env)
        if poll_seconds <= 0 or claim_timeout <= 0:
            raise ConfigError("WORKER_POLL_SECONDS and CLAIM_TIMEOUT_SECONDS must be positive")
        inference = InferenceSettings.from_env(env)
        if inference.embedding_dimension <= 0:
            raise ConfigError("EMBEDDING_DIMENSION must be positive")
        try:
            prices = load_model_prices(env)
            require_prices(prices, [inference.embedding_model, inference.llm_model])
        except UnpricedModelError as exc:
            raise ConfigError(f"MODEL_PRICES: {exc}") from exc
        except ValueError as exc:
            raise ConfigError(f"MODEL_PRICES: {exc}") from exc
        return cls(
            database_url=env_required("DATABASE_URL", env),
            s3_endpoint=env_required("S3_ENDPOINT", env),
            s3_bucket=env_required("S3_BUCKET", env),
            s3_access_key=env_required("S3_ACCESS_KEY", env),
            s3_secret_key=env_required("S3_SECRET_KEY", env),
            s3_region=env_optional("S3_REGION", env) or "us-east-1",
            inference=inference,
            auth=AuthSettings.from_env(env),
            rate_limit=RateLimitSettings.from_env(env),
            max_upload_bytes=env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024, env),
            chunk_tokens=chunk_tokens,
            chunk_overlap_tokens=overlap,
            embed_batch_size=env_int("EMBED_BATCH_SIZE", 64, env),
            summary_input_tokens=env_int("SUMMARY_INPUT_TOKENS", 6000, env),
            summary_max_tokens=env_int("SUMMARY_MAX_TOKENS", 300, env),
            worker_poll_seconds=float(poll_seconds),
            claim_timeout_seconds=claim_timeout,
            log_level=env_optional("LOG_LEVEL", env) or "INFO",
            model_prices=prices,
        )
