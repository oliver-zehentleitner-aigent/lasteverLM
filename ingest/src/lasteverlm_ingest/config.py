"""Settings, read from the environment once at startup.

A missing required value is a startup failure, not a runtime surprise:
`Settings.from_env` raises `ConfigError` with the variable name.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from lasteverlm_ingest.contracts import ModelPrices, parse_model_prices, require_prices


class ConfigError(RuntimeError):
    pass


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required environment variable {name}")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    inference_base_url: str
    inference_api_key: str
    embedding_model: str
    embedding_dimension: int
    llm_model: str
    summary_input_tokens: int
    summary_max_tokens: int
    auth_jwt_secret: str | None
    demo_token: str | None
    max_upload_bytes: int
    chunk_tokens: int
    chunk_overlap_tokens: int
    embed_batch_size: int
    worker_poll_seconds: float
    claim_timeout_seconds: int
    log_level: str
    model_prices: ModelPrices = field(default_factory=dict)
    service_name: str = "ingest"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        jwt_secret = _optional(env, "AUTH_JWT_SECRET")
        demo_token = _optional(env, "DEMO_TOKEN")
        if jwt_secret is None and demo_token is None:
            raise ConfigError("set AUTH_JWT_SECRET and/or DEMO_TOKEN")
        chunk_tokens = _int(env, "CHUNK_TOKENS", 800)
        overlap = _int(env, "CHUNK_OVERLAP_TOKENS", 100)
        if not 0 <= overlap < chunk_tokens:
            raise ConfigError("CHUNK_OVERLAP_TOKENS must be >= 0 and smaller than CHUNK_TOKENS")
        poll_seconds = _int(env, "WORKER_POLL_SECONDS", 2)
        claim_timeout = _int(env, "CLAIM_TIMEOUT_SECONDS", 600)
        if poll_seconds <= 0 or claim_timeout <= 0:
            raise ConfigError("WORKER_POLL_SECONDS and CLAIM_TIMEOUT_SECONDS must be positive")
        dimension = _int(env, "EMBEDDING_DIMENSION", 1536)
        if dimension <= 0:
            raise ConfigError("EMBEDDING_DIMENSION must be positive")
        try:
            prices = parse_model_prices(env.get("MODEL_PRICES"))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        embedding_model = _required(env, "EMBEDDING_MODEL")
        llm_model = _required(env, "LLM_MODEL")
        try:
            require_prices(prices, [embedding_model, llm_model])
        except ValueError as exc:
            raise ConfigError(f"EMBEDDING_MODEL/LLM_MODEL: {exc}") from exc
        return cls(
            database_url=_required(env, "DATABASE_URL"),
            s3_endpoint=_required(env, "S3_ENDPOINT"),
            s3_bucket=_required(env, "S3_BUCKET"),
            s3_access_key=_required(env, "S3_ACCESS_KEY"),
            s3_secret_key=_required(env, "S3_SECRET_KEY"),
            s3_region=env.get("S3_REGION", "").strip() or "us-east-1",
            inference_base_url=_required(env, "INFERENCE_BASE_URL").rstrip("/"),
            inference_api_key=_required(env, "INFERENCE_API_KEY"),
            embedding_model=embedding_model,
            embedding_dimension=dimension,
            llm_model=llm_model,
            summary_input_tokens=_int(env, "SUMMARY_INPUT_TOKENS", 6000),
            summary_max_tokens=_int(env, "SUMMARY_MAX_TOKENS", 300),
            model_prices=prices,
            auth_jwt_secret=jwt_secret,
            demo_token=demo_token,
            max_upload_bytes=_int(env, "MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            chunk_tokens=chunk_tokens,
            chunk_overlap_tokens=overlap,
            embed_batch_size=_int(env, "EMBED_BATCH_SIZE", 64),
            worker_poll_seconds=float(poll_seconds),
            claim_timeout_seconds=claim_timeout,
            log_level=env.get("LOG_LEVEL", "").strip() or "INFO",
        )
