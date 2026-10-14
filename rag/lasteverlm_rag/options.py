"""Generation options per output kind: language for every kind; voice,
speed, style and the second voice of a conversation for audio.

The catalogue is served to the web (``GET /api/rag/outputs/options``) so
nothing is hardcoded there. Voices are the platform's (Qwen3-TTS
CustomVoice speakers; gender and native language from the model card);
every voice speaks all listed languages, its native one best. Languages
are the ten the speech model supports, offered for every kind so the list
is the same everywhere. The speed range is what the UI offers inside the
endpoint's accepted 0.25-4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class Language:
    code: str
    label: str
    english: str  # the name the generator prompt uses


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    gender: str
    language: str


LANGUAGES = [
    Language("en", "English", "English"),
    Language("de", "Deutsch", "German"),
    Language("fr", "Français", "French"),
    Language("es", "Español", "Spanish"),
    Language("it", "Italiano", "Italian"),
    Language("pt", "Português", "Portuguese"),
    Language("ru", "Русский", "Russian"),
    Language("zh", "中文", "Chinese"),
    Language("ja", "日本語", "Japanese"),
    Language("ko", "한국어", "Korean"),
]
VOICES = [
    Voice("ryan", "Ryan", "male", "en"),
    Voice("aiden", "Aiden", "male", "en"),
    Voice("vivian", "Vivian", "female", "zh"),
    Voice("serena", "Serena", "female", "zh"),
    Voice("uncle_fu", "Uncle Fu", "male", "zh"),
    Voice("dylan", "Dylan", "male", "zh"),
    Voice("eric", "Eric", "male", "zh"),
    Voice("ono_anna", "Ono Anna", "female", "ja"),
    Voice("sohee", "Sohee", "female", "ko"),
]
SPEED_MIN, SPEED_MAX, SPEED_STEP, SPEED_DEFAULT = 0.75, 1.5, 0.25, 1.0

TEXT_OPTIONS = ["language"]
KIND_OPTIONS: dict[OutputKind, list[str]] = {
    "report": TEXT_OPTIONS,
    "quiz": TEXT_OPTIONS,
    "table": TEXT_OPTIONS,
    "mindmap": TEXT_OPTIONS,
    "infographic": TEXT_OPTIONS,
    "audio": ["language", "voice", "speed", "audio_style", "audio_voice_2"],
}
AUDIO_STYLES = ["overview", "story", "conversation"]
DEFAULT_AUDIO_STYLE = "overview"

_LANGUAGE_BY_CODE = {lang.code: lang for lang in LANGUAGES}
_VOICE_IDS = {v.id for v in VOICES}


class OutputOptions(BaseModel):
    """What a client may send; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    voice: str | None = None
    speed: float | None = None
    audio_style: str | None = None
    audio_voice_2: str | None = None


def resolve(kind: OutputKind, options: OutputOptions | None, default_voice: str) -> dict[str, Any]:
    """The options as stored on the output: validated for the kind, audio's
    defaults filled in. ``language`` stays absent when not given (the
    document follows the language of its sources). Raises ``ValueError``."""
    given = options.model_dump(exclude_none=True) if options else {}
    allowed = KIND_OPTIONS[kind]
    for key in given:
        if key not in allowed:
            raise ValueError(f"{key}: not an option of {kind}")
    if "language" in given and given["language"] not in _LANGUAGE_BY_CODE:
        raise ValueError(f"language: unknown code {given['language']!r}")
    if "voice" in given and given["voice"] not in _VOICE_IDS:
        raise ValueError(f"voice: unknown voice {given['voice']!r}")
    if "speed" in given:
        speed = given["speed"]
        steps = (speed - SPEED_MIN) / SPEED_STEP
        if not SPEED_MIN <= speed <= SPEED_MAX or abs(steps - round(steps)) > 1e-9:
            raise ValueError(
                f"speed: {speed} is not between {SPEED_MIN} and {SPEED_MAX} "
                f"in steps of {SPEED_STEP}"
            )
    if "audio_style" in given and given["audio_style"] not in AUDIO_STYLES:
        raise ValueError(f"audio_style: unknown style {given['audio_style']!r}")
    if "audio_voice_2" in given and given["audio_voice_2"] not in _VOICE_IDS:
        raise ValueError(f"audio_voice_2: unknown voice {given['audio_voice_2']!r}")
    if kind == "audio":
        given.setdefault("voice", default_voice)
        given.setdefault("speed", SPEED_DEFAULT)
        given.setdefault("audio_style", DEFAULT_AUDIO_STYLE)
        if given["audio_style"] == "conversation":
            given.setdefault("audio_voice_2", second_voice(given["voice"]))
            if given["audio_voice_2"] == given["voice"]:
                raise ValueError("audio_voice_2: must differ from voice")
        elif "audio_voice_2" in given:
            raise ValueError("audio_voice_2: only for the conversation style")
    return given


def second_voice(voice_id: str) -> str:
    """The expert's default voice in a conversation: the next voice with the
    same native language as the interviewer's, in catalogue order, so both
    speak the material's language equally well; ``ryan`` when there is none."""
    native = next(v.language for v in VOICES if v.id == voice_id)
    same = [v.id for v in VOICES if v.language == native]
    if len(same) > 1:
        return same[(same.index(voice_id) + 1) % len(same)]
    return "ryan"


def language_name(code: str | None) -> str | None:
    """The English name for the prompt, e.g. ``de`` -> ``German``."""
    return _LANGUAGE_BY_CODE[code].english if code in _LANGUAGE_BY_CODE else None


def is_voice(voice_id: str) -> bool:
    return voice_id in _VOICE_IDS


def catalogue(default_voice: str) -> dict[str, Any]:
    return {
        "languages": [{"code": lang.code, "label": lang.label} for lang in LANGUAGES],
        "audio": {
            "voices": [
                {"id": v.id, "label": v.label, "gender": v.gender, "language": v.language}
                for v in VOICES
            ],
            "default_voice": default_voice,
            "styles": AUDIO_STYLES,
            "default_style": DEFAULT_AUDIO_STYLE,
            "speed": {
                "min": SPEED_MIN,
                "max": SPEED_MAX,
                "step": SPEED_STEP,
                "default": SPEED_DEFAULT,
            },
        },
        "kinds": KIND_OPTIONS,
    }
