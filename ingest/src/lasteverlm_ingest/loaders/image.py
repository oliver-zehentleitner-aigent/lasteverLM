"""Images: the language model reads them.

The platform's chat model accepts images, so an image source becomes
text in one model call: everything legible transcribed, then a
description of what the image shows. That text is chunked, embedded and
summarized like any other source. The call is billed, so this loader
implements `ModelLoader` and the worker checks the credit before it and
records its usage after it.
"""

from __future__ import annotations

import base64
from typing import Any

from lasteverlm_core import CompletionResult, ProviderError, Usage, thinking_body
from openai import APIError, BadRequestError

from lasteverlm_ingest.loaders import BilledLoaderError, LoaderError, Passage

SYSTEM_PROMPT = (
    "You turn an image into text for a search index. First transcribe every "
    "legible piece of text in the image verbatim, keeping its line structure. "
    "Then describe what the image shows: the kind of image, the objects and "
    "people, and for charts, diagrams and tables the values, labels and "
    "relations they convey. The description must be written in the same "
    "language as the text in the image: German text, German description; "
    "French text, French description. Only an image without any text is "
    "described in English. No preamble, no markdown headings."
)


def sniff_image_type(data: bytes) -> str | None:
    """The media type from the file's first bytes, never from its name."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImageLoader:
    def __init__(self, client: Any, model: str, *, max_tokens: int = 2000) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def load_with_usage(self, data: bytes) -> tuple[list[Passage], Usage]:
        media_type = sniff_image_type(data)
        if media_type is None:
            raise LoaderError("not a PNG, JPEG, WebP or GIF image")
        url = f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]},
                ],
                extra_body=thinking_body(False),
            )
        except BadRequestError as exc:
            # The platform refused this image; another attempt sends the same bytes.
            raise LoaderError(f"the model could not read the image: {exc.message}") from exc
        except APIError as exc:
            raise ProviderError(f"image request failed: {exc}") from exc
        if not response.choices:
            raise ProviderError("provider returned no choices")
        text = (response.choices[0].message.content or "").strip()
        usage = response.usage
        result = CompletionResult(
            text,
            Usage(
                "llm",
                self._model,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            ),
            finish_reason=response.choices[0].finish_reason,
        )
        if not result.text:
            # The model looked and found nothing (a blank image): asking
            # again gives the same answer and bills it again.
            raise BilledLoaderError("the image holds no readable content", result.usage)
        return [Passage(text=result.text)], result.usage
