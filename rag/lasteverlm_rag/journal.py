"""The finished model calls of one output job, kept until it ends.

A job that another worker takes over (a handover at a deploy, a retry
after a transient failure, a stale claim) runs again from the top. Every
model call it makes is looked up here first, by its request: a call
already made returns its stored result, with no provider call and no
usage row, so paid work is never paid again. Retrieval and the checks
cost nothing and simply run again; when the notebook changed meanwhile,
the request differs and the call is made fresh.

It holds model output derived from the user's sources: it lives on the
output's row (gone with the output, with the user, and cleared once the
output is ready or failed) and is never logged. Its size is capped.

A request made twice in one run (the judge's second try of an unusable
answer) is told apart by how often it came before, so the second try is
a real call again.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from typing import Any

from lasteverlm_core import CompletionResult, DecisionResult, EmbeddingResult, Usage

from .store import Store

# what one output's journal may hold: a result larger than an entry may, or
# one that would pass the total, is not kept (that call is made again on a
# takeover), never an error
ENTRY_MAX_BYTES = 256 * 1024
JOURNAL_MAX_BYTES = 4 * 1024 * 1024


def _usage(entry: dict[str, Any]) -> Usage:
    return Usage(entry["kind"], entry["model"], entry["tokens_in"], entry["tokens_out"])


def _usage_entry(usage: Usage) -> dict[str, Any]:
    return {
        "kind": usage.kind,
        "model": usage.model,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
    }


class Journal:
    """The output's journal (``outputs.checkpoint``), loaded at the job's
    start. ``worker_id`` fences the writes: a worker that lost the claim
    adds nothing."""

    def __init__(
        self, store: Store, output_id: str, worker_id: str | None, entries: dict[str, Any]
    ) -> None:
        self._store = store
        self._output_id = output_id
        self._worker_id = worker_id
        self._entries = dict(entries)
        self._seen: dict[str, int] = {}
        self._bytes = sum(len(json.dumps(e)) for e in self._entries.values())
        self._lock = threading.Lock()
        self.replayed = 0

    def _key(self, request: list[Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(request, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        with self._lock:
            self._seen[digest] = self._seen.get(digest, 0) + 1
            return f"{digest}#{self._seen[digest]}"

    def _replay(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self.replayed += 1
            return entry

    def _keep(self, key: str, entry: dict[str, Any]) -> None:
        size = len(json.dumps(entry))
        with self._lock:
            if size > ENTRY_MAX_BYTES or self._bytes + size > JOURNAL_MAX_BYTES:
                return
            self._entries[key] = entry
            self._bytes += size
        self._store.add_checkpoint(self._output_id, self._worker_id, key, entry)

    def complete(
        self, request: list[Any], call: Callable[[], CompletionResult]
    ) -> tuple[CompletionResult, bool]:
        """A completion, from the journal or made now; True when replayed."""
        key = self._key(["complete", *request])
        entry = self._replay(key)
        if entry is not None:
            return (
                CompletionResult(entry["text"], _usage(entry["usage"]), entry.get("finish_reason")),
                True,
            )
        result = call()
        if not result.text.strip():
            # an empty reply is a provider failure: never answered from here
            return result, False
        self._keep(
            key,
            {
                "text": result.text,
                "usage": _usage_entry(result.usage),
                "finish_reason": result.finish_reason,
            },
        )
        return result, False

    def embed(
        self, texts: list[str], model: str, call: Callable[[], EmbeddingResult]
    ) -> tuple[EmbeddingResult, bool]:
        key = self._key(["embed", model, texts])
        entry = self._replay(key)
        if entry is not None:
            return EmbeddingResult(entry["vectors"], _usage(entry["usage"])), True
        result = call()
        self._keep(key, {"vectors": result.vectors, "usage": _usage_entry(result.usage)})
        return result, False

    def decide(
        self, request: list[Any], call: Callable[[], DecisionResult]
    ) -> tuple[DecisionResult, bool]:
        key = self._key(["decide", *request])
        entry = self._replay(key)
        if entry is not None:
            return DecisionResult(entry["answers"], _usage(entry["usage"])), True
        result = call()
        self._keep(key, {"answers": result.answers, "usage": _usage_entry(result.usage)})
        return result, False
