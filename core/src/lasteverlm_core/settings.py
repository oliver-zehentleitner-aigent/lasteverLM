"""Reading configuration from the environment, failing loud.

Every service has its own settings object; what they share is how a
missing or malformed value is reported (a `ConfigError` naming the
variable, at startup) and the loader for the inference endpoint, which
more than one service needs. The model prices load in `pricing.py`, the
authentication settings in `auth.py`, each next to what uses them.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, get_args

VULTR_INFERENCE_BASE_URL = "https://api.vultrinference.com/v1"
DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
# `clef-flash` answers the same questions at half the price per token.
DEFAULT_DECISION_MODEL = "clef"
# The opt-in answer judge: a level picks the model that checks an answer.
# rag measured the defaults (rag/docs/judge-eval.md): low is the cheapest per
# call, which is deepseek, since the GLM models reason even with thinking off.
JudgeLevel = Literal["low", "medium", "high"]
JUDGE_LEVELS: tuple[JudgeLevel, ...] = get_args(JudgeLevel)
DEFAULT_JUDGE_MODELS: Mapping[JudgeLevel, str] = {
    "low": "deepseek-v4.1-flash",
    "medium": "glm-5.3-flash",
    "high": "glm-5.3",
}


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


def parse_judge_models(raw: str | None) -> dict[JudgeLevel, str]:
    """Merge the `JUDGE_MODELS` JSON over the defaults, level by level.

    Empty or unset keeps the defaults. An unknown level or a blank model is
    a `ConfigError`. Whether every model has a price is checked by the
    service that runs the judge (`require_prices`), not here: other services
    read these settings without using the judge.
    """
    models: dict[JudgeLevel, str] = dict(DEFAULT_JUDGE_MODELS)
    if raw is None or not raw.strip():
        return models
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JUDGE_MODELS is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError("JUDGE_MODELS must be a JSON object keyed by level")
    for level, model in parsed.items():
        if level not in JUDGE_LEVELS:
            raise ConfigError(
                f"JUDGE_MODELS has unknown level {level!r}; levels are {', '.join(JUDGE_LEVELS)}"
            )
        if not isinstance(model, str) or not model.strip():
            raise ConfigError(f"JUDGE_MODELS[{level!r}] must be a model name")
        models[level] = model.strip()
    return models


@dataclass(frozen=True)
class InferenceSettings:
    """The OpenAI-compatible inference endpoint ingest and rag talk to.

    `embedding_model` and `embedding_dimension` must be identical in both
    services, which is why they are loaded by one function. `embedding_dimension`
    is requested from the provider on every call, so it is the width of the
    vectors, not a description of the model's native width. `stt_model`
    (`STT_MODEL`) transcribes audio sources; `decision_model`
    (`DECISION_MODEL`) answers the Decision output's typed questions;
    `judge_models` (`JUDGE_MODELS`) maps a judge level to the model that
    checks an answer, billed as an ordinary `llm` call under that model.
    """

    base_url: str
    api_key: str
    llm_model: str
    llm_max_tokens: int
    embedding_model: str
    embedding_dimension: int
    llm_timeout_seconds: int = 60
    stt_model: str = DEFAULT_STT_MODEL
    decision_model: str = DEFAULT_DECISION_MODEL
    judge_models: Mapping[JudgeLevel, str] = field(
        default_factory=lambda: dict(DEFAULT_JUDGE_MODELS)
    )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> InferenceSettings:
        """Read the env; `ConfigError` names a missing key, a value below 1, bad `JUDGE_MODELS`."""
        settings = cls(
            base_url=env_optional("INFERENCE_BASE_URL", env) or VULTR_INFERENCE_BASE_URL,
            api_key=env_required("INFERENCE_API_KEY", env),
            llm_model=env_required("LLM_MODEL", env),
            llm_max_tokens=env_int("LLM_MAX_TOKENS", 1024, env),
            embedding_model=env_required("EMBEDDING_MODEL", env),
            embedding_dimension=env_int("EMBEDDING_DIMENSION", 1536, env),
            llm_timeout_seconds=env_int("LLM_TIMEOUT_SECONDS", 60, env),
            stt_model=env_optional("STT_MODEL", env) or DEFAULT_STT_MODEL,
            decision_model=env_optional("DECISION_MODEL", env) or DEFAULT_DECISION_MODEL,
            judge_models=parse_judge_models(env_optional("JUDGE_MODELS", env)),
        )
        if settings.llm_max_tokens < 1:
            raise ConfigError("LLM_MAX_TOKENS must be at least 1")
        if settings.embedding_dimension < 1:
            raise ConfigError("EMBEDDING_DIMENSION must be at least 1")
        if settings.llm_timeout_seconds < 1:
            raise ConfigError("LLM_TIMEOUT_SECONDS must be at least 1")
        return settings
