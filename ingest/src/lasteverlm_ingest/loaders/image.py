"""Images, and PDF pages without a text layer: the language model reads them.

The platform's chat model accepts images, so an image becomes text in one
model call: everything legible transcribed, then a description of what it
shows. That text is chunked, embedded and summarized like any other
source. Every call is billed: loaders built on `VisionReader` are
`ModelLoader`s and hand each call's usage to the worker's `bill` callback
the moment it returns, which records it and stops the source when the
credit is gone.

An answer that degenerated into a repetition loop (loaders/degeneration.py)
is asked for once more with settings against repetition; a second loop
fails the source, and neither answer is indexed.
"""

from __future__ import annotations

import base64
from typing import Any

from lasteverlm_core import ProviderError, Usage, thinking_body
from openai import APIError, BadRequestError

from lasteverlm_ingest.loaders import Bill, LoaderError, Passage
from lasteverlm_ingest.loaders.degeneration import REASON, degenerated

IMAGE_PROMPT = (
    "You turn an image into text for a search index. First transcribe every "
    "legible piece of text in the image verbatim, keeping its line structure. "
    "Then describe what the image shows: the kind of image, the objects and "
    "people, and for charts, diagrams and tables the values, labels and "
    "relations they convey. The description must be written in the same "
    "language as the text in the image: German text, German description; "
    "French text, French description. Only an image without any text is "
    "described in English. No preamble, no markdown headings."
)
PAGE_PROMPT = (
    "You turn one page of a document into text for a search index. Transcribe "
    "all text on the page verbatim in reading order, keeping headings, lists "
    "and table rows on their own lines. Then, only if the page has figures, "
    "charts, diagrams or photos, describe each briefly with the values and "
    "labels it shows. Write in the language of the page. No preamble, no "
    "markdown headings, nothing about the page being a scan."
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


# The second attempt after a repetition loop: penalties against repeated
# tokens (accepted by the platform, 2026-10-15) and a temperature above
# the first attempt's 0, so the model does not take the same path again.
RETRY_TEMPERATURE = 0.4
RETRY_PENALTIES = {"frequency_penalty": 0.5, "presence_penalty": 0.3}
RETRY_BODY = {"repetition_penalty": 1.15}


class DegeneratedError(LoaderError):
    """Both answers were repetition loops; `usages` are the billed calls,
    which the caller still records."""

    def __init__(self, usages: list[Usage]) -> None:
        super().__init__(REASON)
        self.usages = usages


class VisionReader:
    """A chat-completion call with one image; returns the answer text and
    the usage of every call it made: one, or two when the first answer
    degenerated into a repetition loop. An empty answer is a valid answer
    (a blank image), never an error here; two loops are
    `DegeneratedError`."""

    def __init__(self, client: Any, model: str, *, max_tokens: int = 2000) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def read(self, data: bytes, media_type: str, prompt: str) -> tuple[str, list[Usage]]:
        url = f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
        text, usage, capped = self._call(url, prompt, retry=False)
        if not degenerated(text, capped=capped):
            return text, [usage]
        again, second, capped = self._call(url, prompt, retry=True)
        if degenerated(again, capped=capped):
            raise DegeneratedError([usage, second])
        return again, [usage, second]

    def _call(self, url: str, prompt: str, *, retry: bool) -> tuple[str, Usage, bool]:
        settings: dict[str, Any] = (
            {"temperature": RETRY_TEMPERATURE, **RETRY_PENALTIES} if retry else {"temperature": 0.0}
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]},
                ],
                extra_body={**thinking_body(False), **(RETRY_BODY if retry else {})},
                **settings,
            )
        except BadRequestError as exc:
            # The platform refused this image; another attempt sends the same bytes.
            raise LoaderError(f"the model could not read the image: {exc.message}") from exc
        except APIError as exc:
            raise ProviderError(f"image request failed: {exc}") from exc
        if not response.choices:
            raise ProviderError("provider returned no choices")
        usage = response.usage
        choice = response.choices[0]
        return (
            (choice.message.content or "").strip(),
            Usage(
                "llm",
                self._model,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            ),
            getattr(choice, "finish_reason", None) == "length",
        )


class ImageLoader:
    def __init__(self, vision: VisionReader) -> None:
        self._vision = vision

    @property
    def model(self) -> str:
        return self._vision.model

    def load_billed(self, data: bytes, bill: Bill) -> list[Passage]:
        media_type = sniff_image_type(data)
        if media_type is None:
            raise LoaderError("not a PNG, JPEG, WebP or GIF image")
        try:
            text, usages = self._vision.read(data, media_type, IMAGE_PROMPT)
        except DegeneratedError as exc:
            for usage in exc.usages:
                bill(usage)
            raise
        for usage in usages:
            bill(usage)
        if not text:
            # The model looked and found nothing (a blank image): asking
            # again gives the same answer and bills it again.
            raise LoaderError("the image holds no readable content")
        return [Passage(text=text)]
