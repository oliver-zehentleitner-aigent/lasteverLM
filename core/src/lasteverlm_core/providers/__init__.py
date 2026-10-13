"""Provider interfaces, one implementation each over an OpenAI-compatible API."""

from .base import (
    LLM,
    CompletionResult,
    Embedder,
    EmbeddingResult,
    ProviderError,
    TextToSpeech,
    Usage,
)
from .openai_compat import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TTS_VOICE,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    OpenAICompatibleTextToSpeech,
    make_client,
    thinking_body,
)

__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TTS_VOICE",
    "LLM",
    "CompletionResult",
    "Embedder",
    "EmbeddingResult",
    "OpenAICompatibleEmbedder",
    "OpenAICompatibleLLM",
    "OpenAICompatibleTextToSpeech",
    "ProviderError",
    "TextToSpeech",
    "Usage",
    "make_client",
    "thinking_body",
]
