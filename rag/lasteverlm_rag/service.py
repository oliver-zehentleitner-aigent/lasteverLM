"""The two flows this service owns.

``RagService.ask``: check credit, retrieve, answer, cite, persist, account.
``OutputService``: the API side creates, lists, shares and deletes outputs;
the worker side (``process``) takes a claimed job, waits for the sources,
generates, and indexes the result as a generated source so chat can cite it.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from lasteverlm_core import (
    LLM,
    Answer,
    CompletionResult,
    Embedder,
    Message,
    Output,
    OutputKind,
    ProviderError,
    SharedOutput,
    TokenWindowChunker,
)

from .citations import map_citations, number_passages
from .models import GeneratedOutput, OutputRow, Passage
from .outputs import OutputGenerator
from .outputs._base import GenerationFailed
from .store import Retriever, Store

log = logging.getLogger(__name__)

REFUSAL = "The sources in this notebook do not contain information about that."

ANSWER_SYSTEM_PROMPT = """\
You answer questions strictly from the numbered passages the user provides.

Rules:
- Use only the passages. Do not add facts from your own knowledge.
- Cite every claim with the passage number in square brackets, like [2] or [1, 3].
- Cite only numbers that exist in the passages.
- If the passages do not contain the answer, say so in one sentence and do not guess.
- Be concise. Plain text, no headings."""

ANSWER_MAX_TOKENS = 1024
MAX_ATTEMPTS = 3
SUMMARY_MAX_CHARS = 500


class NotebookNotFound(Exception):
    """No notebook with that id belongs to the caller."""


class OutputNotFound(Exception):
    """No output with that id belongs to the caller."""


class OutputNotReady(Exception):
    """The output exists but has no generated source to ask about yet."""


class InsufficientCredit(Exception):
    """The caller's balance is zero; no provider call is made."""


def render_answer_prompt(question: str, passages: list[Passage]) -> str:
    blocks = []
    for p in passages:
        where = f"{p.source_name}, page {p.page}" if p.page is not None else p.source_name
        blocks.append(f"[{p.n}] ({where})\n{p.text}")
    return "Passages:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


class RagService:
    def __init__(
        self,
        store: Store,
        retriever: Retriever,
        embedder: Embedder,
        llm: LLM,
        retrieval_k: int,
        similarity_floor: float,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._embedder = embedder
        self._llm = llm
        self._k = retrieval_k
        self._floor = similarity_floor

    def ask(
        self, user_id: str, notebook_id: str, question: str, output_id: str | None = None
    ) -> Answer:
        require_notebook(self._store, user_id, notebook_id)
        source_id = self._scope_source(user_id, notebook_id, output_id)
        require_credit(self._store, user_id)
        question = question.strip()

        embedded = self._embedder.embed([question])
        self._store.record_usage(user_id, notebook_id, embedded.usage)
        chunks = self._retriever.search(
            notebook_id, embedded.vectors[0], self._k, self._floor, source_id
        )

        if chunks:
            passages = number_passages(chunks)
            completion = self._llm.complete(
                ANSWER_SYSTEM_PROMPT, render_answer_prompt(question, passages), ANSWER_MAX_TOKENS
            )
            self._store.record_usage(user_id, notebook_id, completion.usage)
            if not completion.text.strip():
                # A reasoning model can spend the whole budget on thinking and return no
                # content; that is a provider failure, never a stored (empty) answer.
                raise ProviderError("the model returned no answer")
            answer, citations = map_citations(completion.text, passages)
        else:
            # Nothing relevant: say so without asking the model, so the answer can
            # never come from model knowledge alone.
            answer, citations = REFUSAL, []

        # Both messages are written only once the answer exists, so the history
        # never holds a question without its answer.
        self._store.insert_message(notebook_id, "user", question, None)
        stored = self._store.insert_message(
            notebook_id, "assistant", answer, [c.model_dump(mode="json") for c in citations]
        )
        return Answer(message_id=stored.id, answer=answer, citations=citations)

    def messages(self, user_id: str, notebook_id: str) -> list[Message]:
        require_notebook(self._store, user_id, notebook_id)
        return self._store.list_messages(notebook_id)

    def _scope_source(self, user_id: str, notebook_id: str, output_id: str | None) -> str | None:
        if output_id is None:
            return None
        output = self._store.get_output(output_id)
        if output is None or output.owner != user_id or output.notebook_id != notebook_id:
            raise OutputNotFound(output_id)
        if output.status != "ready" or output.source_id is None:
            raise OutputNotReady(output_id)
        return output.source_id


class OutputService:
    def __init__(
        self,
        store: Store,
        retriever: Retriever,
        embedder: Embedder,
        llm: LLM,
        generators: dict[OutputKind, OutputGenerator],
        retrieval_k: int,
        similarity_floor: float,
        chunker: TokenWindowChunker | None = None,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._embedder = embedder
        self._llm = llm
        self._generators = generators
        self._k = retrieval_k
        self._floor = similarity_floor
        self._chunker = chunker or TokenWindowChunker()

    # -- API-facing ----------------------------------------------------------

    def create(self, user_id: str, notebook_id: str, kind: OutputKind) -> Output:
        require_notebook(self._store, user_id, notebook_id)
        require_credit(self._store, user_id)
        states = self._store.source_states(notebook_id)
        waiting = any(s.status == "processing" for s in states)
        row = self._store.create_output(notebook_id, kind, "waiting" if waiting else "processing")
        return to_output(row)

    def list(self, user_id: str, notebook_id: str) -> list[Output]:
        require_notebook(self._store, user_id, notebook_id)
        return [to_output(r) for r in self._store.list_outputs(notebook_id)]

    def get(self, user_id: str, output_id: str) -> Output:
        return to_output(self._owned(user_id, output_id))

    def delete(self, user_id: str, output_id: str) -> None:
        row = self._owned(user_id, output_id)
        if row.source_id is not None:
            self._store.delete_source(row.source_id)
        self._store.delete_output(row.id)

    def share(self, user_id: str, output_id: str) -> str:
        row = self._owned(user_id, output_id)
        if row.share_token:
            return row.share_token
        token = secrets.token_urlsafe(24)
        self._store.update_output(row.id, share_token=token)
        return token

    def unshare(self, user_id: str, output_id: str) -> None:
        row = self._owned(user_id, output_id)
        self._store.update_output(row.id, share_token=None)

    def shared(self, token: str) -> SharedOutput:
        row = self._store.get_shared_output(token) if token else None
        if row is None or row.status != "ready":
            raise OutputNotFound(token)
        return SharedOutput.model_validate(
            {
                "kind": row.kind,
                "title": row.title,
                "content": row.content,
                "created_at": row.created_at,
            }
        )

    # -- worker side ---------------------------------------------------------

    def process(self, job: OutputRow) -> bool:
        """Handle one claimed job (the claim already counted the attempt).

        Returns True when the job ended in ``ready`` or ``failed``, False when it
        was given back to the queue for another attempt. A ``GenerationFailed``
        (nothing to generate from, a model that cannot follow the schema, a kind
        that is not available) is final at once: retrying would spend the user's
        credit on the same outcome. Anything else (a provider or database error)
        is retried until ``MAX_ATTEMPTS``; a worker that died mid-run shows up as
        an abandoned claim and costs one attempt too. Every failure lands in the
        row with its error, never in a log only.
        """
        source_id: str | None = None
        try:
            self._store.update_output(job.id, status="processing")
            generated = self._generate(job.owner, job)
            source_id = self._index(job.owner, job.notebook_id, generated)
            self._store.update_output(
                job.id,
                status="ready",
                title=generated.title,
                content=generated.content,
                source_id=source_id,
                error=None,
            )
            return True
        except Exception as exc:
            if source_id is not None:
                self._store.delete_source(source_id)
            error = _error_text(exc)
            final = isinstance(exc, GenerationFailed) or job.attempts >= MAX_ATTEMPTS
            log.warning(
                "output %s (%s) attempt %d failed%s: %s",
                job.id,
                job.kind,
                job.attempts,
                "" if final else ", will retry",
                error,
            )
            if final:
                self._store.update_output(job.id, status="failed", error=error)
                return True
            self._store.release_output(job.id, error=error)
            return False

    def _generate(self, user_id: str, row: OutputRow) -> GeneratedOutput:
        generator = self._generators[row.kind]
        notebook = self._store.get_notebook(row.notebook_id) or {}
        summaries = self._store.source_summaries(row.notebook_id)
        if not summaries:
            raise GenerationFailed("the notebook has no ready source")

        embedded = self._embedder.embed([generator.focus_query])
        self._store.record_usage(user_id, row.notebook_id, embedded.usage)
        chunks = self._retriever.search(row.notebook_id, embedded.vectors[0], self._k, self._floor)

        def complete(
            system: str,
            user: str,
            max_tokens: int | None = None,
            *,
            thinking: bool | None = None,
        ) -> CompletionResult:
            result = self._llm.complete(system, user, max_tokens, thinking=thinking)
            self._store.record_usage(user_id, row.notebook_id, result.usage)
            return result

        return generator.generate(
            complete, str(notebook.get("title", "")), summaries, number_passages(chunks)
        )

    def _index(self, user_id: str, notebook_id: str, generated: GeneratedOutput) -> str:
        """Store the document as a source of kind ``generated`` with its chunks
        embedded, so the chat can retrieve and cite it like any upload."""
        summary = " ".join(generated.index_text.split())[:SUMMARY_MAX_CHARS]
        source_id = self._store.create_generated_source(notebook_id, generated.title, summary)
        chunks = self._chunker.chunk_text(generated.index_text)
        if chunks:
            embedded = self._embedder.embed([c.text for c in chunks])
            self._store.record_usage(user_id, notebook_id, embedded.usage)
            self._store.insert_chunks(source_id, notebook_id, chunks, embedded.vectors)
        self._store.set_source_status(source_id, "ready")
        return source_id

    def _owned(self, user_id: str, output_id: str) -> OutputRow:
        row = self._store.get_output(output_id)
        if row is None or row.owner != user_id:
            raise OutputNotFound(output_id)
        return row


def require_notebook(store: Store, user_id: str, notebook_id: str) -> dict[str, Any]:
    notebook = store.get_notebook(notebook_id)
    if notebook is None or str(notebook.get("owner")) != user_id:
        raise NotebookNotFound(notebook_id)
    return notebook


def require_credit(store: Store, user_id: str) -> None:
    if store.balance_cents(user_id) <= 0:
        raise InsufficientCredit(user_id)


def to_output(row: OutputRow) -> Output:
    """Ids and timestamps are strings inside this service; the contract model parses them."""
    return Output.model_validate(
        {
            "id": row.id,
            "notebook_id": row.notebook_id,
            "kind": row.kind,
            "title": row.title,
            "content": row.content,
            "status": row.status,
            "error": row.error,
            "share_token": row.share_token,
            "source_id": row.source_id,
            "created_at": row.created_at,
        }
    )


def _error_text(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__)[:1000]
