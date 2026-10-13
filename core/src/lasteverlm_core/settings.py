"""Reading configuration from the environment, failing loud.

Every service has its own settings object; what they share is how a
missing or malformed value is reported (a `ConfigError` naming the
variable, at startup) and the loader for the inference endpoint, which
more than one service needs. The model prices load in `pricing.py`, the
authentication settings in `auth.py`, each next to what uses them.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

VULTR_INFERENCE_BASE_URL = "https://api.vultrinference.com/v1"


class ConfigError(RuntimeError):
    """A required configuration value is missing or invalid. Raised at startup."""


def env_required(name: str, env: Mapping[str, str] | None = None) -> str:
    """The value of `name`, stripped; `ConfigError` when unset or blank."""
    value = (os.environ if env is None else env).get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def env_optional(name: str, env: Mapping[str, str] | None = None) -> str | None:
    """The value of `name`, stripped, or `None` when unset or blank."""
    return (os.environ if env is None else env).get(name, "").strip() or None


def env_int(name: str, default: int, env: Mapping[str, str] | None = None) -> int:
    """An integer value of `name`, or `default`; `ConfigError` when it is not an integer."""
    raw = env_optional(name, env)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class InferenceSettings:
    """The OpenAI-compatible inference endpoint ingest and rag talk to.

    `embedding_model` and `embedding_dimension` must be identical in both
    services, which is why they are loaded by one function. `embedding_dimension`
    is requested from the provider on every call, so it is the width of the
    vectors, not a description of the model's native width.
    """

    base_url: str
    api_key: str
    llm_model: str
    llm_max_tokens: int
    embedding_model: str
    embedding_dimension: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> InferenceSettings:
        """Read the env; `ConfigError` names a missing key or a width or budget below 1."""
        settings = cls(
            base_url=env_optional("INFERENCE_BASE_URL", env) or VULTR_INFERENCE_BASE_URL,
            api_key=env_required("INFERENCE_API_KEY", env),
            llm_model=env_required("LLM_MODEL", env),
            llm_max_tokens=env_int("LLM_MAX_TOKENS", 1024, env),
            embedding_model=env_required("EMBEDDING_MODEL", env),
            embedding_dimension=env_int("EMBEDDING_DIMENSION", 1536, env),
        )
        if settings.llm_max_tokens < 1:
            raise ConfigError("LLM_MAX_TOKENS must be at least 1")
        if settings.embedding_dimension < 1:
            raise ConfigError("EMBEDDING_DIMENSION must be at least 1")
        return settings
