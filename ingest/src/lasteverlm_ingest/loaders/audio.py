"""Audio: the platform's speech-to-text model transcribes the whole file.

One transcription call per source, billed through the worker's `bill`
callback like a vision call. The platform answers with plain text and no
timestamps, so a recording becomes one passage without a page number and
is chunked like a text file; citations name the source, not a position
in it (see context/audio-sources.md). Format, size and duration are
core's `probe_audio`: the API checks them at upload, the transcriber
again before the call.

A transcript that degenerated into a repetition loop
(loaders/degeneration.py) is asked for once more at `RETRY_TEMPERATURE`:
the speech model honours a temperature (0 by default) and ignores
penalties, so a higher temperature is what can take it off the looping
path. A second loop fails the source; neither transcript is indexed, and
both calls are billed.
"""

from __future__ import annotations

from lasteverlm_core import AudioError, ProviderError, SpeechToText, probe_audio

from lasteverlm_ingest.loaders import Bill, LoaderError, Passage
from lasteverlm_ingest.loaders.degeneration import degenerated

TRANSCRIPT_REASON = "the model's transcript degenerated into repetition"
# The second attempt after a loop; whisper's default is 0.
RETRY_TEMPERATURE = 0.4


class AudioLoader:
    def __init__(self, transcriber: SpeechToText) -> None:
        self._transcriber = transcriber

    @property
    def model(self) -> str:
        return self._transcriber.model

    def load_billed(self, data: bytes, bill: Bill) -> list[Passage]:
        try:
            info = probe_audio(data)
        except AudioError as exc:
            raise LoaderError(str(exc)) from exc
        name = f"audio.{info.format}"
        text = self._transcribe(data, name, bill)
        if degenerated(text):
            text = self._transcribe(data, name, bill, temperature=RETRY_TEMPERATURE)
            if degenerated(text):
                raise LoaderError(TRANSCRIPT_REASON)
        return [Passage(text=text)]

    def _transcribe(
        self, data: bytes, name: str, bill: Bill, temperature: float | None = None
    ) -> str:
        """One billed transcription call; its text."""
        try:
            result = self._transcriber.transcribe(data, name, temperature=temperature)
        except AudioError as exc:
            raise LoaderError(str(exc)) from exc
        except ProviderError as exc:
            if exc.usage is None:
                raise
            # The platform answered and billed the call, but the answer is
            # unusable (no speech, no duration): asking again sends the
            # same bytes and bills them again.
            bill(exc.usage)
            raise LoaderError(str(exc)) from exc
        bill(result.usage)
        return result.text
