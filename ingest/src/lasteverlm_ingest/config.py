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
    S3Settings,
    UnpricedModelError,
    load_model_prices,
    require_prices,
)
from lasteverlm_core.settings import ConfigError, env_int, env_optional, env_required

__all__ = ["ConfigError", "Settings"]


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3: S3Settings
    inference: InferenceSettings
    auth: AuthSettings
    rate_limit: RateLimitSettings
    max_upload_bytes: int
    max_audio_upload_bytes: int
    stt_timeout_seconds: int
    chunk_tokens: int | None  # None: core's default
    chunk_overlap_tokens: int | None  # None: core's default
    embed_batch_size: int
    summary_input_tokens: int
    summary_max_tokens: int
    image_max_tokens: int
    pdf_vision_max_pages: int
    worker_poll_seconds: float
    claim_timeout_seconds: int
    log_level: str
    model_prices: ModelPrices = field(default_factory=dict)
    service_name: Literal["ingest", "rag"] = "ingest"

    def chunker_kwargs(self) -> dict[str, int]:
        """Only what was set explicitly; the rest stays core's default."""
        kwargs = {}
        if self.chunk_tokens is not None:
            kwargs["size"] = self.chunk_tokens
        if self.chunk_overlap_tokens is not None:
            kwargs["overlap"] = self.chunk_overlap_tokens
        return kwargs

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        # Chunk size and overlap default to core's chunker, which is where
        # the family tunes them; set here only to override a deployment.
        chunk_tokens: int | None = env_int("CHUNK_TOKENS", 0, env) or None
        raw_overlap = env_int("CHUNK_OVERLAP_TOKENS", -1, env)
        overlap: int | None = None if raw_overlap < 0 else raw_overlap
        if chunk_tokens is not None and overlap is not None and not overlap < chunk_tokens:
            raise ConfigError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_TOKENS")
        poll_seconds = env_int("WORKER_POLL_SECONDS", 2, env)
        claim_timeout = env_int("CLAIM_TIMEOUT_SECONDS", 600, env)
        if poll_seconds <= 0 or claim_timeout <= 0:
            raise ConfigError("WORKER_POLL_SECONDS and CLAIM_TIMEOUT_SECONDS must be positive")
        stt_timeout = env_int("STT_TIMEOUT_SECONDS", 300, env)
        if not 0 < stt_timeout < claim_timeout:
            raise ConfigError(
                "STT_TIMEOUT_SECONDS must be positive and below CLAIM_TIMEOUT_SECONDS"
            )
        inference = InferenceSettings.from_env(env)
        if inference.embedding_dimension <= 0:
            raise ConfigError("EMBEDDING_DIMENSION must be positive")
        try:
            prices = load_model_prices(env)
            require_prices(
                prices, [inference.embedding_model, inference.llm_model, inference.stt_model]
            )
        except UnpricedModelError as exc:
            raise ConfigError(f"MODEL_PRICES: {exc}") from exc
        except ValueError as exc:
            raise ConfigError(f"MODEL_PRICES: {exc}") from exc
        return cls(
            database_url=env_required("DATABASE_URL", env),
            s3=S3Settings.from_env(env),
            inference=inference,
            auth=AuthSettings.from_env(env),
            rate_limit=RateLimitSettings.from_env(env),
            max_upload_bytes=env_int("MAX_UPLOAD_BYTES", 20 * 1024 * 1024, env),
            # An original that is converted before transcription; MP3 and
            # WAV stay within core's MAX_AUDIO_BYTES. Below the ingress
            # body limit (64m).
            max_audio_upload_bytes=env_int("MAX_AUDIO_UPLOAD_BYTES", 60 * 1024 * 1024, env),
            stt_timeout_seconds=stt_timeout,
            chunk_tokens=chunk_tokens,
            chunk_overlap_tokens=overlap,
            embed_batch_size=env_int("EMBED_BATCH_SIZE", 64, env),
            summary_input_tokens=env_int("SUMMARY_INPUT_TOKENS", 6000, env),
            summary_max_tokens=env_int("SUMMARY_MAX_TOKENS", 300, env),
            image_max_tokens=env_int("IMAGE_MAX_TOKENS", 2000, env),
            pdf_vision_max_pages=env_int("PDF_VISION_MAX_PAGES", 100, env),
            worker_poll_seconds=float(poll_seconds),
            claim_timeout_seconds=claim_timeout,
            log_level=env_optional("LOG_LEVEL", env) or "INFO",
            model_prices=prices,
        )
