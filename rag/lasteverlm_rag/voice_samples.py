"""Voice previews: a short fixed text per language, spoken by one voice at
one speed, synthesized once and then served from object storage.

The key is derived from the request alone
(``samples/<voice>/<speed>/<language>.mp3``), so every later request for
the same combination, from any user, finds the stored file and costs no
model call. The first request pays for it: a sample text is 45 to 80
characters (three to six seconds of audio, under two seconds to
synthesize), priced like any other ``tts`` usage (``MODEL_PRICES`` per
million seconds of generated speech, rounded up to a whole cent by core),
so one cent.
Two first requests racing for the same key may both synthesize; the
second write replaces an identical file.
"""

from __future__ import annotations

from typing import Any

from lasteverlm_core import Storage, TextToSpeech
from pydantic import BaseModel, ConfigDict

from .options import SPEED_DEFAULT, VOICES, OutputOptions, resolve
from .service import require_credit, synthesize_billed
from .store import Store

SAMPLE_URL_EXPIRES_S = 3600
DEFAULT_LANGUAGE = "en"

# "{name}" is the voice's label. One or two sentences, so a preview is a
# few seconds long.
SAMPLE_TEXT = {
    "en": "Hello, this is {name}. This is how I sound when I read your documents aloud.",
    "de": "Hallo, hier ist {name}. So klinge ich, wenn ich deine Dokumente vorlese.",
    "fr": "Bonjour, ici {name}. Voici ma voix quand je lis vos documents à voix haute.",
    "es": "Hola, soy {name}. Así sueno cuando leo tus documentos en voz alta.",
    "it": "Ciao, sono {name}. Ecco come suono quando leggo ad alta voce i tuoi documenti.",
    "pt": "Olá, aqui é {name}. É assim que eu soo quando leio os seus documentos em voz alta.",
    "ru": "Здравствуйте, это {name}. Так звучит мой голос, когда я читаю ваши документы вслух.",
    "zh": "你好，我是{name}。这就是我朗读你的文档时的声音。",
    "ja": "こんにちは、{name}です。あなたの文書を読み上げるときは、こんな声です。",
    "ko": "안녕하세요, {name}입니다. 문서를 소리 내어 읽을 때 제 목소리는 이렇습니다.",
}


class VoiceSampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice: str
    speed: float | None = None
    language: str | None = None


class SpeechUnavailable(Exception):
    """This deployment has no text-to-speech or no object storage."""


class VoiceSamples:
    def __init__(
        self,
        store: Store,
        tts: TextToSpeech | None,
        objects: Storage | None,
    ) -> None:
        self._store = store
        self._tts = tts
        self._objects = objects
        self._labels = {v.id: v.label for v in VOICES}

    def sample(self, user_id: str, request: VoiceSampleRequest) -> dict[str, Any]:
        """``{"url", "cached"}``; raises ``ValueError`` outside the catalogue and
        ``InsufficientCredit`` when a synthesis is needed and the caller has no
        credit, ``ProviderError`` when the synthesis returns no audio."""
        resolved = resolve(
            "audio",
            OutputOptions(voice=request.voice, speed=request.speed, language=request.language),
            default_voice=request.voice,
        )
        voice, speed = resolved["voice"], resolved.get("speed", SPEED_DEFAULT)
        language = resolved.get("language", DEFAULT_LANGUAGE)
        if self._tts is None or self._objects is None:
            raise SpeechUnavailable()
        key = sample_key(voice, speed, language)
        cached = self._objects.exists(key)
        if not cached:
            require_credit(self._store, user_id)
            text = SAMPLE_TEXT[language].format(name=self._labels[voice])
            result = synthesize_billed(
                self._store, self._tts, user_id, None, text, voice=voice, speed=speed
            )
            self._objects.put(key, result.audio, "audio/mpeg")
        return {"url": self._objects.presigned_get(key, SAMPLE_URL_EXPIRES_S), "cached": cached}


def sample_key(voice: str, speed: float, language: str) -> str:
    return f"samples/{voice}/{speed:.2f}/{language}.mp3"
