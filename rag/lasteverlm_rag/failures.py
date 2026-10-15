"""A short, safe name for what failed in a model call: shown to users and
written to the log, never the provider's own message (it can carry
endpoints)."""

from __future__ import annotations

import re

# rag's and core's own ProviderError texts, which carry no provider detail
_KNOWN = [
    (re.compile(r"empty answer \(finish_reason='?(\w+)'?\)"), "empty answer ({0})"),
    (re.compile(r"no JSON object"), "unparseable answer"),
    (re.compile(r"unknown verdict"), "unknown verdict"),
    (re.compile(r"has no reason"), "answer without a reason"),
    (re.compile(r"returned no content"), "empty answer"),
    (re.compile(r"returned no answer"), "empty answer"),
    (re.compile(r"did not parse"), "unparseable answer"),
    (re.compile(r"returned no audio"), "no audio"),
]


def failure_kind(exc: BaseException) -> str:
    """``timeout`` or ``HTTP <status>`` for an SDK error behind it; for rag's
    or core's own failure texts a fixed category; else the class name."""
    cause = exc.__cause__ or exc
    name = type(cause).__name__
    if "Timeout" in name:
        return "timeout"
    status = getattr(cause, "status_code", None)
    if status:
        return f"HTTP {status}"
    message = str(exc)
    for pattern, label in _KNOWN:
        match = pattern.search(message)
        if match:
            return label.format(*match.groups())
    return name


# what the web translates: one stable code per kind of failure
CAUSES = (
    "timeout",
    "rate_limited",
    "provider_error",
    "empty_answer",
    "truncated_answer",
    "unparseable_answer",
    "no_audio",
    "unknown",
)


def failure_cause(exc: BaseException) -> str:
    """``failure_kind`` as one of ``CAUSES``: what an error response carries
    as ``cause``, for the web to say in the user's language."""
    kind = failure_kind(exc)
    if kind == "timeout":
        return "timeout"
    if kind == "HTTP 429":
        return "rate_limited"
    if kind.startswith("HTTP "):
        return "provider_error"
    if kind == "empty answer (length)":
        return "truncated_answer"
    if kind.startswith("empty answer"):
        return "empty_answer"
    if kind in ("unparseable answer", "unknown verdict", "answer without a reason"):
        return "unparseable_answer"
    if kind == "no audio":
        return "no_audio"
    return "unknown"
