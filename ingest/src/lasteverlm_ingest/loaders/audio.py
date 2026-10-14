"""Audio: the platform's speech-to-text model transcribes the whole file.

One transcription call per source, billed through the worker's `bill`
callback like a vision call. The platform answers with plain text and no
timestamps, so a recording becomes one passage without a page number and
is chunked like a text file; citations name the source, not a position
in it (see context/audio-sources.md). Format, size and duration are
core's `probe_audio`: the API checks them at upload, the transcriber
again before the call.
"""

from __future__ import annotations

from lasteverlm_core import AudioError, ProviderError, SpeechToText, probe_audio

from lasteverlm_ingest.loaders import Bill, LoaderError, Passage


class AudioLoader:
    def __init__(self, transcriber: SpeechToText) -> None:
        self._transcriber = transcriber

    @property
    def model(self) -> str:
        return self._transcriber.model

    def load_billed(self, data: bytes, bill: Bill) -> list[Passage]:
        try:
            info = probe_audio(data)
            result = self._transcriber.transcribe(data, f"audio.{info.format}")
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
        return [Passage(text=result.text)]
