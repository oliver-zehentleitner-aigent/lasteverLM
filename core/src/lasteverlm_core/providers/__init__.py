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
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    OpenAICompatibleTextToSpeech,
    make_client,
)

__all__ = [
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
]
