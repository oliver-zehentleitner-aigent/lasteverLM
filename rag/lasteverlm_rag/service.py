"""The two flows this service owns.

``RagService.ask``: check credit, retrieve, answer, cite, persist, account.
``OutputService``: the API side creates, lists, shares and deletes outputs;
the worker side (``process``) takes a claimed job, waits for the sources,
generates, and indexes the result as a generated source so chat can cite it.
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

from lasteverlm_core import (
    DEFAULT_TTS_VOICE,
    LLM,
    Answer,
    ChunkView,
    CompletionResult,
    Embedder,
    Message,
    Output,
    OutputKind,
    ProviderError,
    SharedOutput,
    Storage,
    TextToSpeech,
    TokenWindowChunker,
    Usage,
    object_key,
)

from .citations import map_citations, number_passages
from .coverage import balance, per_source_quota, uncovered_sources
from .models import (
    Conversation,
    ConversationRow,
    GeneratedOutput,
    NotebookDocument,
    OutputRow,
    Passage,
    RetrievedChunk,
    SourceSummary,
)
from .options import OutputOptions, language_name, resolve
from .outputs import OutputGenerator
from .outputs._base import GenerationFailed
from .speech import split_for_speech
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
- Earlier turns of the conversation, when given, only tell you what the question
  refers to; facts and citations come from the passages alone.
- The notebook's documents are listed below: uploaded sources and documents
  generated from them. A question about which documents the notebook holds is
  answered from that list, without a citation; what a document says comes from
  the passages only.
- A document marked "not in scope" was deselected by the user: its content is
  not searched. Asked about it, say that it is not selected.
- A generated document restates the uploads: when an uploaded passage says the
  same as a generated one, cite the uploaded one.
- Be concise. Plain text, no headings."""

# How the document list names a kind: an upload by its format, a generated
# document by the output it is.
_DOCUMENT_KINDS = {
    "pdf": "PDF",
    "text": "text",
    "url": "web page",
    "image": "image",
    "report": "report",
    "quiz": "quiz",
    "table": "table",
    "mindmap": "mind map",
    "infographic": "infographic",
    "audio": "audio overview",
    "generated": "document",
}

ANSWER_MAX_TOKENS = 1024
# A scoped question is bounded by its one document already: no similarity floor
# (a summary-type question matches no chunk strongly) and a larger k.
SCOPED_RETRIEVAL_K = 12
MAX_ATTEMPTS = 3
SUMMARY_MAX_CHARS = 500
# The model sees the newest turns of the conversation, each cut to a bound, so a
# follow-up ("and how do I install it?") can be resolved without a long chat
# filling the context window.
HISTORY_MESSAGES = 6
HISTORY_MESSAGE_CHARS = 1000
DEFAULT_TITLE = re.compile(r"^Chat (\d+)$")
_MARKERS = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
AUDIO_URL_EXPIRES_S = 3600
AUDIO_FILE = "audio.mp3"


class NotebookNotFound(Exception):
    """No notebook with that id belongs to the caller."""


class OutputNotFound(Exception):
    """No output with that id belongs to the caller."""


class InvalidOptions(Exception):
    """The output options do not fit the kind or the catalogue."""


class ChunkNotFound(Exception):
    """No chunk with that id in a source of the caller's."""


class ConversationNotFound(Exception):
    """No conversation with that id belongs to the caller (in that notebook)."""


class OutputNotReady(Exception):
    """The output exists but has no generated source to ask about yet."""


class InvalidSources(Exception):
    """A selected source id is not an uploaded source of the notebook."""


class InsufficientCredit(Exception):
    """The caller's balance is zero; no provider call is made."""


def answer_system_prompt(
    documents: list[NotebookDocument], selected: list[str] | None = None
) -> str:
    """The answer rules plus the notebook's documents, so a question about the
    notebook itself ("which documents can you see?") has something to go on.
    With a selection, the uploads outside it are marked "not in scope"."""
    lines = [f"- {_document_line(d, selected)}" for d in documents]
    return ANSWER_SYSTEM_PROMPT + "\n\nDocuments in this notebook:\n" + "\n".join(lines)


def _document_line(document: NotebookDocument, selected: list[str] | None) -> str:
    if document.kind == "generated":
        return (
            f"{_DOCUMENT_KINDS[document.output_kind or document.kind]} (generated): {document.name}"
        )
    origin = "uploaded"
    if selected and document.source_id not in selected:
        origin = "uploaded, not in scope"
    return f"{_DOCUMENT_KINDS[document.kind]} ({origin}): {document.name}"


def uploads_first(
    uploads: list[RetrievedChunk], generated: list[RetrievedChunk], k: int, slots: int
) -> list[RetrievedChunk]:
    """The k best chunks of both searches, of which at most ``slots`` are
    generated, uploads listed first: a generated chunk takes the place of a
    weaker upload, but an original always precedes its paraphrase."""
    candidates = [*uploads, *generated[:slots]]
    best = sorted(candidates, key=lambda c: c.similarity, reverse=True)[:k]
    kept = {c.chunk_id for c in best}
    # each search's own order is kept; only membership comes from the scores
    return [c for c in candidates if c.chunk_id in kept]


def render_answer_prompt(
    question: str, passages: list[Passage], history: list[Message] | None = None
) -> str:
    blocks = []
    for p in passages:
        where = f"{p.source_name}, page {p.page}" if p.page is not None else p.source_name
        blocks.append(f"[{p.n}] ({where})\n{p.text}")
    listed = "\n\n".join(blocks) if blocks else "(no passage matched the question)"
    prompt = "Passages:\n\n" + listed + f"\n\nQuestion: {question}"
    if not history:
        return prompt
    # earlier answers lose their markers: their numbers point at other passages
    turns = [
        f"{'User' if m.role == 'user' else 'Assistant'}: "
        f"{_MARKERS.sub('', m.content)[:HISTORY_MESSAGE_CHARS]}"
        for m in history
    ]
    return "Conversation so far:\n\n" + "\n".join(turns) + "\n\n" + prompt


class RagService:
    def __init__(
        self,
        store: Store,
        retriever: Retriever,
        embedder: Embedder,
        llm: LLM,
        retrieval_k: int,
        similarity_floor: float,
        generated_slots: int = 0,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._embedder = embedder
        self._llm = llm
        self._k = retrieval_k
        self._floor = similarity_floor
        self._generated_slots = generated_slots

    def ask(
        self,
        user_id: str,
        notebook_id: str,
        question: str,
        conversation_id: str,
        output_id: str | None = None,
        source_ids: list[str] | None = None,
    ) -> Answer:
        require_notebook(self._store, user_id, notebook_id)
        conversation = self._owned_conversation(user_id, conversation_id)
        if conversation.notebook_id != notebook_id:
            raise ConversationNotFound(conversation_id)
        source_id = self._scope_source(user_id, notebook_id, output_id)
        selected = check_sources(self._store, notebook_id, source_ids)
        require_credit(self._store, user_id)
        question = question.strip()

        embedded = self._embedder.embed([question])
        self._store.record_usage(user_id, notebook_id, embedded.usage)
        chunks = self._retrieve(notebook_id, embedded.vectors[0], source_id, selected)
        documents = self._store.notebook_documents(notebook_id)

        if chunks or documents:
            # Without a matching passage the model still sees the document
            # list, so a question about the notebook itself can be answered.
            passages = number_passages(chunks)
            history = self._store.list_messages(conversation_id, last=HISTORY_MESSAGES)
            completion = self._llm.complete(
                answer_system_prompt(documents, selected),
                render_answer_prompt(question, passages, history),
                ANSWER_MAX_TOKENS,
            )
            self._store.record_usage(user_id, notebook_id, completion.usage)
            if not completion.text.strip():
                # A reasoning model can spend the whole budget on thinking and return no
                # content; that is a provider failure, never a stored (empty) answer.
                raise ProviderError("the model returned no answer")
            answer, citations = map_citations(completion.text, passages)
        else:
            # An empty notebook: say so without asking the model, so the answer
            # can never come from model knowledge alone.
            answer, citations = REFUSAL, []

        # Both messages are written only once the answer exists, so the history
        # never holds a question without its answer.
        self._store.insert_message(notebook_id, conversation_id, "user", question, None)
        stored = self._store.insert_message(
            notebook_id,
            conversation_id,
            "assistant",
            answer,
            [c.model_dump(mode="json") for c in citations],
        )
        return Answer(message_id=stored.id, answer=answer, citations=citations)

    def _retrieve(
        self,
        notebook_id: str,
        vector: list[float],
        source_id: str | None,
        selected: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        # a scope ("ask about this") names one document and wins over the selection
        if source_id:
            return self._retriever.search(notebook_id, vector, SCOPED_RETRIEVAL_K, 0.0, source_id)
        # Unscoped: the uploads fill the k slots by score; a generated document
        # may take a few of them when it scores above the floor too.
        uploads = self._retriever.search(
            notebook_id, vector, self._k, self._floor, source_ids=selected
        )
        generated = (
            self._retriever.search(
                notebook_id, vector, self._generated_slots, self._floor, generated=True
            )
            if self._generated_slots
            else []
        )
        return uploads_first(uploads, generated, self._k, self._generated_slots)

    # -- conversations -------------------------------------------------------

    def conversations(self, user_id: str, notebook_id: str) -> list[Conversation]:
        require_notebook(self._store, user_id, notebook_id)
        return [c.to_api() for c in self._store.list_conversations(notebook_id)]

    def create_conversation(
        self, user_id: str, notebook_id: str, title: str | None = None
    ) -> Conversation:
        require_notebook(self._store, user_id, notebook_id)
        if title is None or not title.strip():
            title = f"Chat {self._next_chat_number(notebook_id)}"
        return self._store.create_conversation(notebook_id, title.strip()).to_api()

    def rename_conversation(self, user_id: str, conversation_id: str, title: str) -> Conversation:
        self._owned_conversation(user_id, conversation_id)
        return self._store.rename_conversation(conversation_id, title).to_api()

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        self._owned_conversation(user_id, conversation_id)
        self._store.delete_conversation(conversation_id)

    def chunk(self, user_id: str, chunk_id: str) -> ChunkView:
        row = self._store.get_chunk(chunk_id, user_id)
        if row is None:
            raise ChunkNotFound(chunk_id)
        return ChunkView.model_validate(row)

    def messages(self, user_id: str, conversation_id: str) -> list[Message]:
        self._owned_conversation(user_id, conversation_id)
        return self._store.list_messages(conversation_id)

    def _next_chat_number(self, notebook_id: str) -> int:
        """One above the highest "Chat n" still open, so a closed tab's number
        can come back but two open tabs never share a default title."""
        numbers = [
            int(m.group(1))
            for c in self._store.list_conversations(notebook_id)
            if (m := DEFAULT_TITLE.match(c.title))
        ]
        return max(numbers, default=0) + 1

    def _owned_conversation(self, user_id: str, conversation_id: str) -> ConversationRow:
        row = self._store.get_conversation(conversation_id)
        if row is None or row.owner != user_id:
            raise ConversationNotFound(conversation_id)
        return row

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
        tts: TextToSpeech | None = None,
        objects: Storage | None = None,
        default_voice: str = DEFAULT_TTS_VOICE,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._embedder = embedder
        self._llm = llm
        self._generators = generators
        self._k = retrieval_k
        self._floor = similarity_floor
        self._chunker = chunker or TokenWindowChunker()
        self._tts = tts
        self._objects = objects
        self._default_voice = default_voice

    # -- API-facing ----------------------------------------------------------

    def create(
        self,
        user_id: str,
        notebook_id: str,
        kind: OutputKind,
        options: OutputOptions | None = None,
        source_ids: list[str] | None = None,
    ) -> Output:
        try:
            resolved = resolve(kind, options, self._default_voice)
        except ValueError as exc:
            raise InvalidOptions(str(exc)) from exc
        require_notebook(self._store, user_id, notebook_id)
        selected = check_sources(self._store, notebook_id, source_ids)
        if selected:
            # stored with the options, so the viewer shows what it was made from
            resolved["sources"] = selected
        require_credit(self._store, user_id)
        states = self._store.source_states(notebook_id)
        waiting = any(s.status == "processing" for s in states)
        row = self._store.create_output(
            notebook_id, kind, "waiting" if waiting else "processing", resolved
        )
        return self._present(row)

    def list(self, user_id: str, notebook_id: str) -> list[Output]:
        require_notebook(self._store, user_id, notebook_id)
        return [self._present(r) for r in self._store.list_outputs(notebook_id)]

    def get(self, user_id: str, output_id: str) -> Output:
        return self._present(self._owned(user_id, output_id))

    def delete(self, user_id: str, output_id: str) -> None:
        row = self._owned(user_id, output_id)
        if row.source_id is not None:
            self._store.delete_source(row.source_id)
        # objects first: a failed delete leaves the row for another try, not an orphan file
        self._delete_objects(row.content)
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
                "content": self._public_content(row.content),
                "created_at": row.created_at,
                # the source selection names the owner's link ids: not for strangers
                "options": {k: v for k, v in row.options.items() if k != "sources"},
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
        content: dict[str, Any] = {}
        try:
            self._store.update_output(job.id, status="processing")
            generated = self._generate(job.owner, job)
            content = generated.content
            if generated.speech is not None:
                content = {"key": self._speak(job, generated.speech)}
            source_id = self._index(job.owner, job.notebook_id, generated)
            self._store.update_output(
                job.id,
                status="ready",
                title=generated.title,
                content=content,
                source_id=source_id,
                error=None,
            )
            log.info(
                "output %s (%s) ready: %r, source %s", job.id, job.kind, generated.title, source_id
            )
            return True
        except Exception as exc:
            if source_id is not None:
                self._store.delete_source(source_id)
            self._delete_objects(content)
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
        selected = row.options.get("sources")
        if selected:
            summaries = [s for s in summaries if s.source_id in selected]
            if not summaries:
                raise GenerationFailed("none of the selected sources is ready")
        if not summaries:
            raise GenerationFailed("the notebook has no ready source")

        embedded = self._embedder.embed([generator.focus_query])
        self._store.record_usage(user_id, row.notebook_id, embedded.usage)
        chunks = balanced_chunks(
            self._retriever,
            row.notebook_id,
            embedded.vectors[0],
            summaries,
            self._k,
            self._floor,
            selected,
        )

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

        generated = generator.generate(
            complete,
            str(notebook.get("title", "")),
            summaries,
            number_passages(chunks),
            language=language_name(row.options.get("language")),
        )
        for name in uncovered_sources(generated.index_text, summaries, chunks):
            # fail-loud light: the document is kept, the gap is visible in the log
            log.warning(
                "output %s (%s) does not mention source %r of its input", row.id, row.kind, name
            )
        return generated

    def _index(self, user_id: str, notebook_id: str, generated: GeneratedOutput) -> str:
        """Store the document as a source of kind ``generated`` with its chunks
        embedded, so the chat can retrieve and cite it like any upload."""
        summary = " ".join(generated.index_text.split())[:SUMMARY_MAX_CHARS]
        source_id = self._store.create_generated_source(notebook_id, generated.title, summary)
        chunks = self._chunker.chunk_text(generated.index_text)
        if chunks:
            embedded = self._embedder.embed([c.text for c in chunks])
            self._store.record_usage(user_id, notebook_id, embedded.usage)
            self._store.insert_chunks(source_id, chunks, embedded.vectors)
        self._store.set_source_status(source_id, "ready")
        return source_id

    def _speak(self, job: OutputRow, script: str) -> str:
        """Synthesize the script segment by segment (one usage row each, priced
        per input character) and store the joined MP3; returns the object key."""
        if self._tts is None or self._objects is None:
            raise GenerationFailed("audio: text-to-speech is not available on this deployment")
        segments = split_for_speech(script)
        if not segments:
            raise GenerationFailed("audio: the script is empty")
        parts: list[bytes] = []
        for segment in segments:
            parts.append(
                self._tts.synthesize(
                    segment, voice=job.options.get("voice"), speed=job.options.get("speed")
                )
            )
            usage = Usage(kind="tts", model=self._tts.model, tokens_in=len(segment), tokens_out=0)
            self._store.record_usage(job.owner, job.notebook_id, usage)
        key = object_key(job.notebook_id, job.id, AUDIO_FILE)
        # MP3 frames are self-contained: the segments concatenate into one stream
        self._objects.put(key, b"".join(parts), "audio/mpeg")
        return key

    def _public_content(self, content: dict[str, Any] | None) -> dict[str, Any] | None:
        """The row keeps the object key; a reader gets a presigned URL instead,
        because an <audio> element cannot send a bearer header."""
        key = (content or {}).get("key")
        if not isinstance(key, str) or self._objects is None:
            return content
        return {"url": self._objects.presigned_get(key, AUDIO_URL_EXPIRES_S)}

    def _delete_objects(self, content: dict[str, Any] | None) -> None:
        key = (content or {}).get("key")
        if isinstance(key, str) and self._objects is not None:
            self._objects.delete(key)

    def _present(self, row: OutputRow) -> Output:
        output = to_output(row)
        return output.model_copy(update={"content": self._public_content(row.content)})

    def _owned(self, user_id: str, output_id: str) -> OutputRow:
        row = self._store.get_output(output_id)
        if row is None or row.owner != user_id:
            raise OutputNotFound(output_id)
        return row


def balanced_chunks(
    retriever: Retriever,
    notebook_id: str,
    vector: list[float],
    summaries: list[SourceSummary],
    k: int,
    floor: float,
    selected: list[str] | None = None,
) -> list[RetrievedChunk]:
    """A generator's focus-query passages with every ready source represented:
    each source's best chunks regardless of the floor, the rest by score."""
    each, total = per_source_quota(len(summaries), k)
    per_source = [retriever.search(notebook_id, vector, each, 0.0, s.source_id) for s in summaries]
    # the rest by score, within the selection when there is one
    ranked = retriever.search(notebook_id, vector, total, floor, source_ids=selected)
    return balance(per_source, ranked, total)


def check_sources(store: Store, notebook_id: str, source_ids: list[str] | None) -> list[str] | None:
    """The selection as link ids, or None for all sources. Every id must be an
    uploaded source of this notebook; a generated document is not selectable."""
    if not source_ids:
        return None
    uploads = {s.source_id for s in store.source_states(notebook_id) if s.kind != "generated"}
    for source_id in source_ids:
        if source_id not in uploads:
            raise InvalidSources(source_id)
    return list(dict.fromkeys(source_ids))


def require_notebook(store: Store, user_id: str, notebook_id: str) -> dict[str, Any]:
    notebook = store.get_notebook(notebook_id)
    if notebook is None or str(notebook.get("owner")) != user_id:
        raise NotebookNotFound(notebook_id)
    return notebook


def require_credit(store: Store, user_id: str) -> None:
    """Core's rule: a positive balance, for admins as for everyone else."""
    if not store.has_credit(user_id):
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
            "options": row.options,
        }
    )


def _error_text(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__)[:1000]
