"""Generation options per output kind: language and the user's own
instructions for every kind; style and length for a report; the number of
questions, difficulty and audience for a quiz; voice, speed, style and the
second voice of a conversation for audio; the question for a decision.

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

TEXT_OPTIONS = ["language", "instructions"]
KIND_OPTIONS: dict[OutputKind, list[str]] = {
    "report": [*TEXT_OPTIONS, "report_style", "length"],
    "quiz": [*TEXT_OPTIONS, "question_count", "difficulty", "audience"],
    "table": TEXT_OPTIONS,
    "mindmap": TEXT_OPTIONS,
    "infographic": TEXT_OPTIONS,
    "audio": [*TEXT_OPTIONS, "voice", "speed", "audio_style", "audio_voice_2"],
    "decision": [*TEXT_OPTIONS, "question", "decision_type", "choices", "levels"],
    # no language: a chart is made from the picked candidates without a model call
    "chart": ["instructions", "charts"],
}
CHART_TYPES = ["bar", "line", "pie", "stacked_bar", "scatter"]
CHARTS_MAX = 12  # picked per output, and proposed per call at most
PROPOSE_DEFAULT = 6
INSTRUCTIONS_MAX_CHARS = 500
REPORT_STYLES = ["briefing", "detailed", "executive_summary", "explainer", "academic"]
DEFAULT_REPORT_STYLE = "briefing"
LENGTHS = ["short", "medium", "long"]
DEFAULT_LENGTH = "medium"
QUESTION_COUNT_MIN, QUESTION_COUNT_MAX, QUESTION_COUNT_DEFAULT = 5, 30, 10
DIFFICULTIES = ["easy", "medium", "hard"]
DEFAULT_DIFFICULTY = "medium"
AUDIENCES = ["children", "teens", "adults", "experts"]
DEFAULT_AUDIENCE = "adults"
AUDIO_STYLES = ["overview", "story", "conversation"]
DEFAULT_AUDIO_STYLE = "overview"
DECISION_TYPES = ["yes_no", "choice", "scale"]
DEFAULT_DECISION_TYPE = "yes_no"
QUESTION_MAX_CHARS = 500
CHOICES_MIN, CHOICES_MAX = 2, 8
LEVELS_MIN, LEVELS_MAX = 3, 7
LABEL_MAX_CHARS = 80

_LANGUAGE_BY_CODE = {lang.code: lang for lang in LANGUAGES}
_VOICE_IDS = {v.id for v in VOICES}


class OutputOptions(BaseModel):
    """What a client may send; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    instructions: str | None = None
    report_style: str | None = None
    length: str | None = None
    question_count: int | None = None
    difficulty: str | None = None
    audience: str | None = None
    voice: str | None = None
    speed: float | None = None
    audio_style: str | None = None
    audio_voice_2: str | None = None
    question: str | None = None
    decision_type: str | None = None
    choices: list[str] | None = None
    levels: list[str] | None = None
    charts: list[dict[str, Any]] | None = None


def resolve(kind: OutputKind, options: OutputOptions | None, default_voice: str) -> dict[str, Any]:
    """The options as stored on the output: validated for the kind, the
    defaults of report, quiz and audio filled in. ``language`` stays absent
    when not given (the document follows the language of its sources), and
    so do empty ``instructions``. Raises ``ValueError``."""
    given = options.model_dump(exclude_none=True) if options else {}
    allowed = KIND_OPTIONS[kind]
    for key in given:
        if key not in allowed:
            raise ValueError(f"{key}: not an option of {kind}")
    if "language" in given and given["language"] not in _LANGUAGE_BY_CODE:
        raise ValueError(f"language: unknown code {given['language']!r}")
    if "instructions" in given:
        text = " ".join(str(given.pop("instructions")).split())
        if len(text) > INSTRUCTIONS_MAX_CHARS:
            raise ValueError(f"instructions: at most {INSTRUCTIONS_MAX_CHARS} characters")
        if text:
            given["instructions"] = text
    for key, allowed_values in (
        ("report_style", REPORT_STYLES),
        ("length", LENGTHS),
        ("difficulty", DIFFICULTIES),
        ("audience", AUDIENCES),
    ):
        if key in given and given[key] not in allowed_values:
            raise ValueError(f"{key}: unknown value {given[key]!r}")
    if "question_count" in given and not (
        QUESTION_COUNT_MIN <= given["question_count"] <= QUESTION_COUNT_MAX
    ):
        raise ValueError(f"question_count: between {QUESTION_COUNT_MIN} and {QUESTION_COUNT_MAX}")
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
    if kind == "report":
        given.setdefault("report_style", DEFAULT_REPORT_STYLE)
        given.setdefault("length", DEFAULT_LENGTH)
    if kind == "quiz":
        given.setdefault("question_count", QUESTION_COUNT_DEFAULT)
        given.setdefault("difficulty", DEFAULT_DIFFICULTY)
        given.setdefault("audience", DEFAULT_AUDIENCE)
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
    if kind == "decision":
        _resolve_decision(given)
    if kind == "chart":
        _resolve_charts(given)
    return given


def _resolve_charts(given: dict[str, Any]) -> None:
    """A chart output needs 1 to 12 picked candidates, each as the proposal
    returned it; their values are checked again by the worker."""
    from pydantic import ValidationError

    from .outputs.chart import Candidate

    charts = given.get("charts") or []
    if not 1 <= len(charts) <= CHARTS_MAX:
        raise ValueError(f"charts: 1 to {CHARTS_MAX} picked candidates")
    try:
        given["charts"] = [Candidate.model_validate(c).model_dump() for c in charts]
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ValueError(f"charts: {where}: {first['msg']}") from exc


def _resolve_decision(given: dict[str, Any]) -> None:
    """A decision needs its question; ``choice`` needs ``choices`` and
    ``scale`` needs ``levels`` (lowest first), each list of distinct, short
    labels; neither list is taken by another type."""
    question = " ".join(str(given.get("question", "")).split())
    if not question:
        raise ValueError("question: a decision needs a question")
    if len(question) > QUESTION_MAX_CHARS:
        raise ValueError(f"question: at most {QUESTION_MAX_CHARS} characters")
    given["question"] = question
    kind = given.setdefault("decision_type", DEFAULT_DECISION_TYPE)
    if kind not in DECISION_TYPES:
        raise ValueError(f"decision_type: unknown type {kind!r}")
    needed = {"choice": "choices", "scale": "levels"}.get(kind)
    for key in ("choices", "levels"):
        if key in given and key != needed:
            raise ValueError(f"{key}: not an option of decision_type {kind}")
    if needed is None:
        return
    low, high = (CHOICES_MIN, CHOICES_MAX) if needed == "choices" else (LEVELS_MIN, LEVELS_MAX)
    labels = [" ".join(str(label).split()) for label in given.get(needed) or []]
    if not low <= len(labels) <= high:
        raise ValueError(f"{needed}: {low} to {high} labels for decision_type {kind}")
    if any(not label or len(label) > LABEL_MAX_CHARS for label in labels):
        raise ValueError(f"{needed}: every label is 1 to {LABEL_MAX_CHARS} characters")
    if len({label.casefold() for label in labels}) != len(labels):
        raise ValueError(f"{needed}: labels must be distinct")
    given[needed] = labels


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
        "instructions": {"max_chars": INSTRUCTIONS_MAX_CHARS},
        "report": {
            "styles": REPORT_STYLES,
            "default_style": DEFAULT_REPORT_STYLE,
            "lengths": LENGTHS,
            "default_length": DEFAULT_LENGTH,
        },
        "quiz": {
            "question_count": {
                "min": QUESTION_COUNT_MIN,
                "max": QUESTION_COUNT_MAX,
                "default": QUESTION_COUNT_DEFAULT,
            },
            "difficulties": DIFFICULTIES,
            "default_difficulty": DEFAULT_DIFFICULTY,
            "audiences": AUDIENCES,
            "default_audience": DEFAULT_AUDIENCE,
        },
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
        "decision": {
            "types": DECISION_TYPES,
            "default_type": DEFAULT_DECISION_TYPE,
            "question_max_chars": QUESTION_MAX_CHARS,
            "choices": {"min": CHOICES_MIN, "max": CHOICES_MAX},
            "levels": {"min": LEVELS_MIN, "max": LEVELS_MAX},
        },
        "chart": {
            "chart_types": CHART_TYPES,
            "charts_max": CHARTS_MAX,
            "propose_max": CHARTS_MAX,
            "propose_default": PROPOSE_DEFAULT,
        },
        "kinds": KIND_OPTIONS,
    }
