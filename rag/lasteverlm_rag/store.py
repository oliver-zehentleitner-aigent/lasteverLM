"""Database access over the shared schema (docs/architecture.md in the parent).

Two interfaces with one PostgreSQL implementation each: ``Retriever`` for the
pgvector similarity search, ``Store`` for everything else this service reads
or writes: notebooks (read), messages, outputs, the generated sources and
their chunks, usage, the credit check and the admin flag. ``notebooks``,
``library_sources``, ``sources`` (a library source linked into a notebook;
its id is the public source id) and ``chunks`` (on the library source) are
ingest's tables; ``usage`` and ``ledger`` belong to core and
account; this module only reads and writes them.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Literal, Protocol

from lasteverlm_core import (
    Chunk,
    Message,
    ModelPrices,
    OutputKind,
    OutputStatus,
    PricingRules,
    PricingRulesCache,
    Role,
    Usage,
    admin_role,
    balance_cents,
    has_credit,
    record_usage,
)
from lasteverlm_core.usage import Connection as CoreConnection
from psycopg import Connection, Cursor
from psycopg.rows import DictRow, TupleRow, dict_row, tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .models import (
    Booking,
    ConversationRow,
    NotebookDocument,
    OutputRow,
    RetrievedChunk,
    SourceState,
    SourceSummary,
)
from .starter import OutputCopy

log = logging.getLogger(__name__)

Pool = ConnectionPool[Connection[DictRow]]

SERVICE_NAME: Literal["rag"] = "rag"


class Retriever(Protocol):
    def search(
        self,
        notebook_id: str,
        embedding: list[float],
        k: int,
        floor: float,
        source_id: str | None = None,
        generated: bool = False,
        source_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]: ...

    def chunks(self, notebook_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        """The chunks among ``chunk_ids`` that belong to a ready source linked
        into the notebook, without a similarity (0)."""
        ...


class Store(Protocol):
    # notebooks (ingest's table, read only)
    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None: ...

    # conversations and their messages
    def list_conversations(self, notebook_id: str) -> list[ConversationRow]: ...

    def get_conversation(self, conversation_id: str) -> ConversationRow | None: ...

    def create_conversation(self, notebook_id: str, title: str) -> ConversationRow: ...

    def rename_conversation(self, conversation_id: str, title: str) -> ConversationRow: ...

    def delete_conversation(self, conversation_id: str) -> None: ...

    def list_messages(self, conversation_id: str, last: int | None = None) -> list[Message]: ...

    def insert_message(
        self,
        notebook_id: str,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None,
        support: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> Message: ...

    def get_message(self, message_id: str) -> tuple[str, Message] | None:
        """The message with its notebook's id."""
        ...

    def update_message_support(self, message_id: str, support: dict[str, Any]) -> None: ...

    def set_message_feedback(self, message_id: str, feedback: dict[str, Any]) -> None: ...

    def feedback_overview(self, days: int, latest: int) -> dict[str, Any]:
        """Ratings per UTC day (``days``, oldest first, each day present) and
        the newest down-rated answers with the question before them."""
        ...

    # a notebook's starting questions, cached by the ready uploads they came from
    def notebook_suggestions(self, notebook_id: str) -> tuple[str, list[str]] | None: ...

    def save_notebook_suggestions(
        self, notebook_id: str, sources_key: str, suggestions: list[str]
    ) -> None: ...

    # outputs
    def create_output(
        self,
        notebook_id: str,
        kind: OutputKind,
        status: OutputStatus,
        options: dict[str, Any] | None = None,
        booking_id: str | None = None,
        reserved_cents: float = 0.0,
    ) -> OutputRow: ...

    # the agent chat's plans
    def create_plan(self, plan: dict[str, Any]) -> None: ...

    def user_preference(self, user_id: str, key: str) -> Any:
        """One of account's per-user preferences (users.preferences), or None."""
        ...

    def get_plan(self, plan_id: str) -> dict[str, Any] | None: ...

    def save_plan(self, plan_id: str, **fields: Any) -> None:
        """``status``, ``steps``, ``confirmed_at``, ``finished_at``; ``plan`` (its
        public shape) goes onto the message that proposed it."""
        ...

    def running_plans(self) -> list[dict[str, Any]]: ...

    def get_output(self, output_id: str) -> OutputRow | None: ...

    def get_shared_output(self, share_token: str) -> OutputRow | None: ...

    def get_shared_notebook(self, share_token: str) -> dict[str, Any] | None:
        """The notebook ingest shares under the token (``notebooks.share_token``)."""
        ...

    def rename_output(self, output_id: str, title: str) -> None:
        """The output's title and its generated source's name, together."""
        ...

    def list_outputs(self, notebook_id: str) -> list[OutputRow]: ...

    def update_output(self, output_id: str, **fields: Any) -> None:
        """Ready or failed also stamps ``finished_at``."""
        ...

    def finish_output(self, output_id: str, worker_id: str, **fields: Any) -> bool:
        """``update_output`` only while ``worker_id`` holds the claim; False
        when another worker took the job over (nothing written)."""
        ...

    def holds_output(self, output_id: str, worker_id: str) -> bool:
        """Whether ``worker_id`` still holds the output's claim."""
        ...

    def get_checkpoint(self, output_id: str) -> dict[str, Any]:
        """The output's journal of finished model calls (``outputs.checkpoint``)."""
        ...

    def add_checkpoint(
        self, output_id: str, worker_id: str | None, key: str, entry: dict[str, Any]
    ) -> None:
        """Keep one finished call in the journal, only while ``worker_id``
        holds the claim (any time without one). Ready or failed clears it."""
        ...

    def hand_over_output(
        self, output_id: str, worker_id: str, phase: dict[str, Any], record: dict[str, Any]
    ) -> bool:
        """Release the claim for another worker while ``worker_id`` holds it:
        claim cleared, the attempt not counted, ``phase`` set and ``record``
        appended to ``attempt_log``. False when the claim was not its own."""
        ...

    def orphaned_generated(self, older_than_s: int) -> list[dict[str, Any]]:
        """Generated library rows older than ``older_than_s`` that no output's
        ``source_id`` points at, as ``{"id", "notebook_ids"}`` (where linked)."""
        ...

    # judgements on request, run by the worker (``judge_jobs``)
    def create_judge_job(self, job: dict[str, Any]) -> None: ...

    def get_judge_job(self, job_id: str) -> dict[str, Any] | None: ...

    def latest_judge_job(self, target: str, target_id: str) -> dict[str, Any] | None:
        """The target's newest job, any status."""
        ...

    def claim_judge_job(self, worker_id: str, stale_after_s: int) -> dict[str, Any] | None:
        """The oldest queued job, or a running one whose claim is stale;
        claiming counts an attempt."""
        ...

    def update_judge_job(self, job_id: str, **fields: Any) -> None:
        """``status``, ``phase``, ``error``; done or failed stamps
        ``finished_at``; every write refreshes the claim."""
        ...

    def add_judge_attempt(self, job_id: str, record: dict[str, Any]) -> None: ...

    def add_attempt(self, output_id: str, record: dict[str, Any]) -> None:
        """Append one failed attempt's record to ``attempt_log``."""
        ...

    def find_outputs(self, id_prefix: str, limit: int) -> list[tuple[OutputRow, str]]:
        """Outputs whose dashless id starts with ``id_prefix`` (lowercase hex),
        newest first, at most ``limit``, each with its owner's email."""
        ...

    def report_outputs(self, output_ids: list[str] | None) -> list[OutputRow]:
        """Ready reports, in the trash or not; only ``output_ids`` when given
        (the report units repair)."""
        ...

    def audio_outputs(self, output_ids: list[str] | None) -> list[OutputRow]:
        """Ready audio outputs with a stored file, in the trash or not; only
        ``output_ids`` when given (the audio repair)."""
        ...

    def delete_output(self, output_id: str) -> None: ...

    # the user's outputs in the library, and their trash
    def list_library_outputs(
        self, owner: str, kind: str | None, trash: bool
    ) -> list[OutputRow]: ...

    def trash_outputs(self, output_ids: list[str]) -> None: ...

    def restore_output(self, output_id: str) -> None: ...

    def expired_outputs(self) -> list[OutputRow]: ...

    # the outputs table as a job queue (worker entrypoint)
    def claim_output(self, worker_id: str, stale_after_s: int) -> OutputRow | None: ...

    # copies of a starter notebook's outputs (``output_copies``, filled by ingest)
    def claim_output_copy(self, worker_id: str, stale_after_s: int) -> OutputCopy | None: ...

    def end_output_copy(self, target_notebook: str, error: str | None, final: bool) -> None:
        """Done: the row goes. Failed: released for another attempt, or kept
        with its error when ``final``."""
        ...

    def copied_outputs(self, notebook_id: str) -> set[str]:
        """The starter outputs already copied into the notebook (``copied_from``)."""
        ...

    def copy_output(
        self,
        row: OutputRow,
        output_id: str,
        target_notebook: str,
        content: dict[str, Any] | None,
        options: dict[str, Any],
        provenance: dict[str, Any] | None,
    ) -> bool:
        """The output's copy in the target notebook (its owner's), with a copy
        of its generated library row, link and chunks, in one transaction;
        False when it was copied already."""
        ...

    def release_output(self, output_id: str, error: str | None = None) -> None: ...

    def touch_output(self, output_id: str, phase: dict[str, Any] | None = None) -> None:
        """Refresh a running job's claim (its worker is alive) and, with
        ``phase``, the step it is in, in one update."""
        ...

    def charged(self, action_id: str) -> bool:
        """Whether any usage row (a call or a fee) was booked under the action."""
        ...

    def waiting_outputs(self, older_than_s: int) -> list[OutputRow]:
        """Outputs still waiting for their sources, created over ``older_than_s`` ago."""
        ...

    # sources and chunks (ingest's tables; rag writes only kind 'generated').
    # A generated source's link and its hidden library row share one id.
    def source_states(self, notebook_id: str) -> list[SourceState]: ...

    def source_summaries(self, notebook_id: str) -> list[SourceSummary]: ...

    def notebook_documents(self, notebook_id: str) -> list[NotebookDocument]: ...

    def create_generated_source(self, notebook_id: str, name: str, summary: str) -> str: ...

    def insert_chunks(
        self, source_id: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None: ...

    def set_source_status(self, source_id: str, status: str, error: str | None = None) -> None: ...

    def delete_source(self, source_id: str) -> None: ...

    # one chunk for its owner (provenance view)
    def get_chunk(self, chunk_id: str, user_id: str) -> dict[str, Any] | None: ...

    # admin overview (read only, across all users)
    def admin_stats(self, stale_after_s: int) -> dict[str, Any]: ...

    def daily_stats(self, days: int) -> list[dict[str, Any]]: ...

    # deleting a user (admin): the user's outputs and rag's rows in their notebooks
    def user_output_contents(self, user_id: str) -> list[dict[str, Any]]: ...

    def delete_user_data(self, user_id: str) -> None: ...

    # credit
    def has_credit(self, user_id: str) -> bool: ...

    def balance_cents(self, user_id: str) -> Decimal: ...

    def held_cents(self, user_id: str) -> Decimal:
        """What the user's started work still holds of the balance: waiting
        outputs' maxima, a running plan's waiting explanations, and the
        source reads ingest funded and has not finished."""
        ...

    def admin_role(self, user_id: str) -> Role: ...

    def record_usage(self, booking: Booking, usage: Usage) -> None:
        """Book one model call under its action; core fixes cost and charge."""
        ...

    def pricing_rules(self) -> PricingRules:
        """Account's pricing rules as bookings use them now."""
        ...


# Top-k by cosine distance inside one notebook, ready sources only, optionally
# one source. Chunks belong to the library source and are reached through the
# notebook's links, so a file linked into several notebooks is searched from
# each; the source id returned is the link's (the id this notebook knows).
# Unscoped, it searches either the uploads or the generated documents
# (``generated``), so the caller can bound how many paraphrases reach the
# model; ``source_ids`` narrows it to the sources the user ticked. The floor
# is applied in SQL so a notebook with no relevant chunk costs one round trip.
_SEARCH_SQL = """
select c.id::text as chunk_id, s.id::text as source_id, l.name as source_name,
       l.kind as source_kind, c.page, c.text, c.idx as chunk_index,
       (select count(*) from chunks n where n.library_source_id = c.library_source_id)
           as chunk_count,
       1 - (c.embedding <=> %(embedding)s::vector) as similarity
from sources s
join library_sources l on l.id = s.library_source_id
join chunks c on c.library_source_id = l.id
where s.notebook_id = %(notebook_id)s
  and l.status = 'ready'
  and (%(source_id)s::uuid is null or s.id = %(source_id)s::uuid)
  and (%(source_id)s::uuid is not null or (l.kind = 'generated') = %(generated)s)
  and (%(source_ids)s::uuid[] is null or s.id = any(%(source_ids)s::uuid[]))
  and 1 - (c.embedding <=> %(embedding)s::vector) >= %(floor)s
order by c.embedding <=> %(embedding)s::vector
limit %(k)s
"""

# Days a trashed output stays: account's per-user preference, read as ingest
# reads it for the library; 14 without a user row or a number.
_TRASH_DAYS = (
    "greatest(0, coalesce((select case when jsonb_typeof(u.preferences -> 'trash_days')"
    " = 'number' then floor((u.preferences ->> 'trash_days')::numeric)::int end"
    " from users u where u.id = {owner}), 14))"
)
# The owner falls back to the notebook's for a row a pod of the previous
# release inserted during the rolling deploy (migration 0004 is expand only).
_OUTPUT_OWNER = "coalesce(o.owner, n.owner)"
_OUTPUT_COLUMNS = f"""
o.id::text as id, o.notebook_id::text as notebook_id, {_OUTPUT_OWNER}::text as owner, o.kind,
o.title, o.content, o.status, o.error, o.share_token, o.source_id::text as source_id,
o.attempts, o.created_at, o.options, o.origin_title, o.deleted_at, o.provenance,
o.booking_id::text as booking_id, o.phase, o.attempt_log, o.finished_at,
o.deleted_at + make_interval(days => {_TRASH_DAYS.format(owner=_OUTPUT_OWNER)}) as purge_at
"""
_OUTPUT_FROM = "from outputs o left join notebooks n on n.id = o.notebook_id"
_OUTPUT_FIELDS = {
    "title",
    "content",
    "status",
    "error",
    "share_token",
    "source_id",
    "provenance",
    "phase",
}

# One job per call, oldest first; rows other workers hold are skipped, a claim
# older than the stale limit (a worker that died mid-job) is taken over, and a
# waiting row is claimable only once no uploaded source of its notebook is
# still processing (of its selection, when it has one: ``options.sources``).
# The claim counts as an attempt.
_CLAIM_SQL = """
with job as (
    select id from outputs x
    where x.status in ('waiting', 'processing') and x.deleted_at is null
      and (x.claimed_at is null or x.claimed_at < now() - make_interval(secs => %(stale)s))
      and not exists (
          select 1 from sources s join library_sources l on l.id = s.library_source_id
          where s.notebook_id = x.notebook_id and l.status = 'processing' and l.kind <> 'generated'
            and (not (x.options ? 'sources') or (x.options -> 'sources') ? s.id::text)
      )
    order by x.created_at, x.id
    for update skip locked
    limit 1
)
update outputs o set claimed_at = now(), claimed_by = %(worker)s, attempts = o.attempts + 1
from job
where o.id = job.id
returning o.id::text as id
"""


class PgVectorRetriever:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def search(
        self,
        notebook_id: str,
        embedding: list[float],
        k: int,
        floor: float,
        source_id: str | None = None,
        generated: bool = False,
        source_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        params = {
            "notebook_id": notebook_id,
            "embedding": _vector_literal(embedding),
            "source_id": source_id,
            "generated": generated,
            "source_ids": source_ids,
            "floor": floor,
            "k": k,
        }
        with self._pool.connection() as conn:
            rows = conn.execute(_SEARCH_SQL, params).fetchall()
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                source_id=r["source_id"],
                source_name=r["source_name"],
                source_kind=r["source_kind"],
                page=r["page"],
                text=r["text"],
                similarity=float(r["similarity"]),
                chunk_index=r["chunk_index"],
                chunk_count=r["chunk_count"],
            )
            for r in rows
        ]

    def chunks(self, notebook_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        with self._pool.connection() as conn:
            rows = conn.execute(_NOTEBOOK_CHUNKS_SQL, (notebook_id, chunk_ids)).fetchall()
        return [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                source_id=r["source_id"],
                source_name=r["source_name"],
                source_kind=r["source_kind"],
                page=r["page"],
                text=r["text"],
                similarity=0.0,
                chunk_index=r["chunk_index"],
                chunk_count=r["chunk_count"],
            )
            for r in rows
        ]


_PLAN_SQL = (
    "select id::text as id, conversation_id::text as conversation_id, "
    "notebook_id::text as notebook_id, owner::text as owner, status, steps, estimate, "
    "action_id::text as action_id, message_id::text as message_id, question, "
    "coalesce(notes, '[]'::jsonb) as notes, coalesce(sources, '[]'::jsonb) as sources, "
    "created_at, confirmed_at, finished_at from plans"
)

# One copy job per call, oldest first, as the output queue claims: rows other
# workers hold are skipped, a stale claim is taken over, a row that failed
# for good (its error kept) is not claimed again. The claim counts an attempt.
_CLAIM_COPY_SQL = """
with job as (
    select target_notebook from output_copies
    where error is null
      and (claimed_at is null or claimed_at < now() - make_interval(secs => %(stale)s))
    order by created_at, target_notebook
    for update skip locked
    limit 1
)
update output_copies c
set claimed_at = now(), claimed_by = %(worker)s, attempts = c.attempts + 1
from job
where c.target_notebook = job.target_notebook
returning c.target_notebook::text as target_notebook, c.source_notebook::text as source_notebook,
          c.owner::text as owner, c.source_map, c.chunk_map, c.attempts
"""

# Chunks by id, only from ready sources linked into the notebook: a chart's
# values are checked again against the passages its proposal cited.
_NOTEBOOK_CHUNKS_SQL = """
select c.id::text as chunk_id, s.id::text as source_id, l.name as source_name,
       l.kind as source_kind, c.page, c.idx as chunk_index, c.text,
       (select count(*) from chunks n where n.library_source_id = c.library_source_id)
           as chunk_count
from sources s
join library_sources l on l.id = s.library_source_id
join chunks c on c.library_source_id = l.id
where s.notebook_id = %s and l.status = 'ready' and c.id = any(%s::uuid[])
"""

_CHUNK_SQL = """
select c.id::text as chunk_id, s.id::text as source_id, l.name as source_name,
       l.kind as source_kind, c.page, c.idx as chunk_index,
       (select count(*) from chunks n where n.library_source_id = c.library_source_id)
           as chunk_count,
       c.text
from chunks c
join library_sources l on l.id = c.library_source_id
join sources s on s.library_source_id = l.id
join notebooks nb on nb.id = s.notebook_id
where c.id = %(chunk_id)s and l.owner = %(user_id)s and nb.owner = %(user_id)s
order by s.created_at, s.id
limit 1
"""

# Ratings per UTC day of their (last) change, every day of the window present.
_FEEDBACK_DAYS_SQL = """
with d as (
    select (now() at time zone 'utc')::date - i as day
    from generate_series(0, %(days)s - 1) as i
)
select d.day,
       count(m.id) filter (where m.feedback ->> 'rating' = 'up') as up,
       count(m.id) filter (where m.feedback ->> 'rating' = 'down') as down
from d left join messages m
  on m.feedback is not null
 and ((m.feedback ->> 'at')::timestamptz at time zone 'utc')::date = d.day
group by d.day
order by d.day
"""

# The newest down-rated answers, each with the user's question right before it.
_FEEDBACK_DOWN_SQL = """
select m.id::text as message_id, m.notebook_id::text as notebook_id,
       (m.feedback ->> 'at')::timestamptz as at, m.feedback ->> 'comment' as comment,
       m.content as answer,
       (select q.content from messages q
        where q.conversation_id = m.conversation_id and q.role = 'user'
          and (q.created_at, q.id) < (m.created_at, m.id)
        order by q.created_at desc, q.id desc limit 1) as question
from messages m
where m.feedback ->> 'rating' = 'down'
order by (m.feedback ->> 'at')::timestamptz desc, m.id
limit %(latest)s
"""

_DAILY_SQL = """
with span as (
    select (now() at time zone 'utc')::date - (%(days)s - 1) as first_day
), d as (
    select first_day + i as day from span, generate_series(0, %(days)s - 1) as i
), since as (
    select first_day::timestamp at time zone 'utc' as at from span
), m as (
    select (created_at at time zone 'utc')::date as day, count(*) as n
    from messages, since where created_at >= since.at group by 1
), o as (
    select (created_at at time zone 'utc')::date as day, kind, count(*) as n
    from outputs, since where created_at >= since.at group by 1, 2
)
select d.day, coalesce(max(m.n), 0) as messages,
       coalesce(jsonb_object_agg(o.kind, o.n) filter (where o.kind is not null), '{}') as by_kind
from d
left join m on m.day = d.day
left join o on o.day = d.day
group by d.day
order by d.day
"""

_CONVERSATION_COLUMNS = (
    "c.id::text as id, c.notebook_id::text as notebook_id, n.owner::text as owner, "
    "c.title, c.created_at"
)
_CONVERSATION_FROM = "from conversations c join notebooks n on n.id = c.notebook_id"


_USER_NOTEBOOKS = "select id from notebooks where owner = %(owner)s"


# What a user's started work still holds: rag's waiting outputs and a
# running plan's waiting explanations, and ingest's funded reads not finished
# (ingest's columns, see ingest's README: funded_cents with funded_request_at).
_HELD_SQL = """
select
    coalesce((select sum(reserved_cents) from outputs
              where owner = %(owner)s and status in ('waiting', 'processing')
              and deleted_at is null), 0)
  + coalesce((select sum((s->'estimate'->>'max')::numeric)
              from plans p, jsonb_array_elements(p.steps) s
              where p.owner = %(owner)s and p.status = 'running'
              and s->>'tool' = 'explain_output' and s->>'state' in ('waiting', 'running')), 0)
  + coalesce((select sum(funded_cents) from library_sources
              where owner = %(owner)s and funded_request_at is not null
              and status = 'processing' and deleted_at is null), 0)
  as held
"""


_JUDGE_JOB_SELECT = (
    "select id::text as id, owner::text as owner, target, target_id::text as target_id, "
    "notebook_id::text as notebook_id, level, status, phase, attempts, attempt_log, error, "
    "created_at, finished_at from judge_jobs"
)
# a judgement on request: the oldest queued job, or one whose worker died
_CLAIM_JUDGE_SQL = """
with job as (
    select id from judge_jobs
    where status = 'queued'
       or (status = 'running' and claimed_at < now() - make_interval(secs => %(stale)s))
    order by created_at, id
    for update skip locked
    limit 1
)
update judge_jobs j set status = 'running', claimed_at = now(), claimed_by = %(worker)s,
    attempts = j.attempts + 1
from job where j.id = job.id
returning j.id::text as id
"""


def _judge_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row),
        "created_at": str(row["created_at"]),
        "finished_at": _str_or_none(row["finished_at"]),
        "attempt_log": list(row["attempt_log"] or []),
    }


class PostgresStore:
    def __init__(self, pool: Pool, prices: ModelPrices) -> None:
        self._pool = pool
        self._prices = prices
        # account's pricing rules (margins, fees), re-read at most every 30 s
        self._rules = PricingRulesCache()

    # -- notebooks --------------------------------------------------------

    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select id::text as id, owner::text as owner, title from notebooks where id = %s",
                (notebook_id,),
            ).fetchone()
        return dict(row) if row else None

    # -- messages ---------------------------------------------------------

    def list_conversations(self, notebook_id: str) -> list[ConversationRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_CONVERSATION_COLUMNS} {_CONVERSATION_FROM} "
                "where c.notebook_id = %s order by c.created_at, c.id",
                (notebook_id,),
            ).fetchall()
        return [ConversationRow(**r) for r in rows]

    def get_conversation(self, conversation_id: str) -> ConversationRow | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"select {_CONVERSATION_COLUMNS} {_CONVERSATION_FROM} where c.id = %s",
                (conversation_id,),
            ).fetchone()
        return ConversationRow(**row) if row else None

    def create_conversation(self, notebook_id: str, title: str) -> ConversationRow:
        conversation_id = _new_id()
        with self._pool.connection() as conn:
            conn.execute(
                "insert into conversations (id, notebook_id, title) values (%s, %s, %s)",
                (conversation_id, notebook_id, title),
            )
        row = self.get_conversation(conversation_id)
        assert row is not None
        return row

    def rename_conversation(self, conversation_id: str, title: str) -> ConversationRow:
        with self._pool.connection() as conn:
            conn.execute(
                "update conversations set title = %s where id = %s", (title, conversation_id)
            )
        row = self.get_conversation(conversation_id)
        assert row is not None
        return row

    def delete_conversation(self, conversation_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("delete from conversations where id = %s", (conversation_id,))

    def list_messages(self, conversation_id: str, last: int | None = None) -> list[Message]:
        """Oldest first; with ``last``, only the newest ``last`` messages."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select * from (select id::text as id, role, content, citations, support, "
                "suggestions, feedback, plan, created_at "
                "from messages where conversation_id = %s "
                "order by created_at desc, id desc limit %s) m order by created_at, id",
                (conversation_id, last),
            ).fetchall()
        return [_to_message(r) for r in rows]

    def insert_message(
        self,
        notebook_id: str,
        conversation_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None,
        support: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
        plan: dict[str, Any] | None = None,
    ) -> Message:
        with self._pool.connection() as conn:
            row = conn.execute(
                "insert into messages "
                "(id, notebook_id, conversation_id, role, content, citations, support, "
                "suggestions, plan) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "returning id::text as id, role, content, citations, support, suggestions, "
                "feedback, plan, created_at",
                (
                    _new_id(),
                    notebook_id,
                    conversation_id,
                    role,
                    content,
                    _jsonb(citations),
                    _jsonb(support),
                    Jsonb(suggestions or []),
                    _jsonb(plan),
                ),
            ).fetchone()
        assert row is not None
        return _to_message(row)

    def get_message(self, message_id: str) -> tuple[str, Message] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select notebook_id::text as notebook_id, id::text as id, role, content, "
                "citations, support, suggestions, feedback, plan, created_at "
                "from messages where id = %s",
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        notebook_id = row.pop("notebook_id")
        return notebook_id, _to_message(row)

    def update_message_support(self, message_id: str, support: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update messages set support = %s where id = %s", (_jsonb(support), message_id)
            )

    def set_message_feedback(self, message_id: str, feedback: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update messages set feedback = %s where id = %s", (Jsonb(feedback), message_id)
            )

    def feedback_overview(self, days: int, latest: int) -> dict[str, Any]:
        with self._pool.connection() as conn:
            per_day = conn.execute(_FEEDBACK_DAYS_SQL, {"days": days}).fetchall()
            down = conn.execute(_FEEDBACK_DOWN_SQL, {"latest": latest}).fetchall()
        return {"days": [dict(r) for r in per_day], "latest_down": [dict(r) for r in down]}

    def notebook_suggestions(self, notebook_id: str) -> tuple[str, list[str]] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select sources_key, suggestions from notebook_suggestions "
                "where notebook_id = %s",
                (notebook_id,),
            ).fetchone()
        return (row["sources_key"], list(row["suggestions"])) if row else None

    def save_notebook_suggestions(
        self, notebook_id: str, sources_key: str, suggestions: list[str]
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "insert into notebook_suggestions (notebook_id, sources_key, suggestions) "
                "values (%s, %s, %s) on conflict (notebook_id) do update set "
                "sources_key = excluded.sources_key, suggestions = excluded.suggestions, "
                "created_at = now()",
                (notebook_id, sources_key, Jsonb(suggestions)),
            )

    # -- outputs ----------------------------------------------------------

    def create_output(
        self,
        notebook_id: str,
        kind: OutputKind,
        status: OutputStatus,
        options: dict[str, Any] | None = None,
        booking_id: str | None = None,
        reserved_cents: float = 0.0,
    ) -> OutputRow:
        output_id = _new_id()
        with self._pool.connection() as conn:
            conn.execute(
                "insert into outputs (id, notebook_id, owner, origin_title, kind, title, "
                "status, options, booking_id, reserved_cents) "
                "select %s, n.id, n.owner, n.title, %s, '', %s, %s, %s, %s "
                "from notebooks n where n.id = %s",
                (
                    output_id,
                    kind,
                    status,
                    Jsonb(options or {}),
                    booking_id,
                    reserved_cents,
                    notebook_id,
                ),
            )
        row = self.get_output(output_id)
        assert row is not None
        return row

    def create_plan(self, plan: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "insert into plans (id, conversation_id, notebook_id, owner, status, steps, "
                "estimate, action_id, message_id, question, notes, sources) values (%(id)s, "
                "%(conversation_id)s, %(notebook_id)s, %(owner)s, %(status)s, %(steps)s, "
                "%(estimate)s, %(action_id)s, %(message_id)s, %(question)s, %(notes)s, "
                "%(sources)s)",
                {
                    **plan,
                    "steps": Jsonb(plan["steps"]),
                    "estimate": Jsonb(plan["estimate"]),
                    "question": _jsonb(plan.get("question")),
                    "notes": Jsonb(plan.get("notes") or []),
                    "sources": Jsonb(plan.get("sources") or []),
                },
            )

    def user_preference(self, user_id: str, key: str) -> Any:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select preferences -> %s as value from users where id = %s", (key, user_id)
            ).fetchone()
        return row["value"] if row else None

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(_PLAN_SQL + " where id = %s", (plan_id,)).fetchone()
        return dict(row) if row else None

    def save_plan(self, plan_id: str, **fields: Any) -> None:
        public = fields.pop("plan", None)
        unknown = set(fields) - {
            "status",
            "steps",
            "estimate",
            "question",
            "notes",
            "sources",
            "confirmed_at",
            "finished_at",
        }
        if unknown:
            raise ValueError(f"not an updatable plans column: {sorted(unknown)}")
        for name in ("steps", "estimate", "question", "notes", "sources"):
            if name in fields:
                fields[name] = _jsonb(fields[name])
        assignments = ", ".join(f"{name} = %({name})s" for name in fields)
        with self._pool.connection() as conn, conn.transaction():
            if fields:
                conn.execute(
                    f"update plans set {assignments} where id = %(id)s",
                    {**fields, "id": plan_id},
                )
            if public is not None:
                conn.execute(
                    "update messages m set plan = %s from plans p "
                    "where p.id = %s and m.id = p.message_id",
                    (Jsonb(public), plan_id),
                )

    def running_plans(self) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                _PLAN_SQL + " where status = 'running' order by confirmed_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_output(self, output_id: str) -> OutputRow | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where o.id = %s", (output_id,)
            ).fetchone()
        return _to_output(row) if row else None

    def get_shared_output(self, share_token: str) -> OutputRow | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where o.share_token = %s", (share_token,)
            ).fetchone()
        return _to_output(row) if row else None

    def get_shared_notebook(self, share_token: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select id::text as id, title from notebooks where share_token = %s",
                (share_token,),
            ).fetchone()
        return dict(row) if row else None

    def rename_output(self, output_id: str, title: str) -> None:
        # the generated source carries the title as its name: chat cites it by that
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("update outputs set title = %s where id = %s", (title, output_id))
            conn.execute(
                "update library_sources l set name = %s from outputs o "
                "where o.id = %s and l.id = o.source_id",
                (title, output_id),
            )

    def list_outputs(self, notebook_id: str) -> list[OutputRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} "
                "where o.notebook_id = %s and o.deleted_at is null order by o.created_at, o.id",
                (notebook_id,),
            ).fetchall()
        return [_to_output(r) for r in rows]

    def list_library_outputs(self, owner: str, kind: str | None, trash: bool) -> list[OutputRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where {_OUTPUT_OWNER} = %(owner)s "
                "and (%(kind)s::text is null or o.kind = %(kind)s) "
                "and (o.deleted_at is not null) = %(trash)s "
                "order by coalesce(o.deleted_at, o.created_at) desc, o.id",
                {"owner": owner, "kind": kind, "trash": trash},
            ).fetchall()
        return [_to_output(r) for r in rows]

    def trash_outputs(self, output_ids: list[str]) -> None:
        """Into the trash: ``deleted_at`` on the outputs and their generated
        library rows, and every link of those rows removed (as ingest's
        library trash does), in one transaction. An output already in the trash
        keeps its date; a generated row it got since follows it."""
        ids = {"ids": output_ids}
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "update library_sources l set deleted_at = now() from outputs o "
                "where o.id = any(%(ids)s::uuid[]) and l.id = o.source_id and l.deleted_at is null",
                ids,
            )
            conn.execute(
                "delete from sources s using outputs o "
                "where o.id = any(%(ids)s::uuid[]) and s.library_source_id = o.source_id",
                ids,
            )
            conn.execute(
                "update outputs set deleted_at = now() "
                "where id = any(%(ids)s::uuid[]) and deleted_at is null",
                ids,
            )

    def restore_output(self, output_id: str) -> None:
        """Out of the trash, with the generated row, linked into the origin
        notebook again if it still exists (the link under the row's id)."""
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "update library_sources l set deleted_at = null from outputs o "
                "where o.id = %s and l.id = o.source_id",
                (output_id,),
            )
            conn.execute(
                "insert into sources (id, notebook_id, library_source_id) "
                "select o.source_id, o.notebook_id, o.source_id from outputs o "
                "where o.id = %s and o.source_id is not null and o.notebook_id is not null "
                "on conflict do nothing",
                (output_id,),
            )
            conn.execute("update outputs set deleted_at = null where id = %s", (output_id,))

    def expired_outputs(self) -> list[OutputRow]:
        """Trashed outputs whose owner's retention has elapsed, oldest first."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where o.deleted_at is not null "
                f"and o.deleted_at + make_interval(days => "
                f"{_TRASH_DAYS.format(owner=_OUTPUT_OWNER)}) <= now() "
                "order by o.deleted_at, o.id"
            ).fetchall()
        return [_to_output(r) for r in rows]

    def update_output(self, output_id: str, **fields: Any) -> None:
        unknown = set(fields) - _OUTPUT_FIELDS
        if unknown:
            raise ValueError(f"not an updatable outputs column: {sorted(unknown)}")
        for name in ("content", "provenance", "phase"):
            if name in fields:
                fields[name] = _jsonb(fields[name])
        assignments = ", ".join(f"{name} = %({name})s" for name in fields)
        if fields.get("status") in ("ready", "failed"):
            # the journal of finished calls is for resuming: done with the job
            assignments += ", finished_at = now(), checkpoint = '{}'::jsonb"
        with self._pool.connection() as conn:
            conn.execute(
                f"update outputs set {assignments} where id = %(id)s", {**fields, "id": output_id}
            )

    def finish_output(self, output_id: str, worker_id: str, **fields: Any) -> bool:
        unknown = set(fields) - _OUTPUT_FIELDS
        if unknown:
            raise ValueError(f"not an updatable outputs column: {sorted(unknown)}")
        for name in ("content", "provenance", "phase"):
            if name in fields:
                fields[name] = _jsonb(fields[name])
        assignments = ", ".join(f"{name} = %({name})s" for name in fields)
        if fields.get("status") in ("ready", "failed"):
            # the journal of finished calls is for resuming: done with the job
            assignments += ", finished_at = now(), checkpoint = '{}'::jsonb"
        with self._pool.connection() as conn:
            cursor = conn.execute(
                f"update outputs set {assignments} where id = %(id)s and claimed_by = %(worker)s",
                {**fields, "id": output_id, "worker": worker_id},
            )
            return cursor.rowcount == 1

    def get_checkpoint(self, output_id: str) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select checkpoint from outputs where id = %s", (output_id,)
            ).fetchone()
        return dict(row["checkpoint"]) if row and row["checkpoint"] else {}

    def add_checkpoint(
        self, output_id: str, worker_id: str | None, key: str, entry: dict[str, Any]
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update outputs set checkpoint = checkpoint || jsonb_build_object(%s::text, %s) "
                "where id = %s and (%s::text is null or claimed_by = %s)",
                (key, Jsonb(entry), output_id, worker_id, worker_id),
            )

    def hand_over_output(
        self, output_id: str, worker_id: str, phase: dict[str, Any], record: dict[str, Any]
    ) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                "update outputs set claimed_by = null, claimed_at = null, "
                "attempts = greatest(attempts - 1, 0), phase = %s, "
                "attempt_log = attempt_log || %s where id = %s and claimed_by = %s",
                (Jsonb(phase), Jsonb([record]), output_id, worker_id),
            )
            return cursor.rowcount == 1

    def holds_output(self, output_id: str, worker_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select claimed_by = %s as held from outputs where id = %s",
                (worker_id, output_id),
            ).fetchone()
        return bool(row and row["held"])

    def orphaned_generated(self, older_than_s: int) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select l.id::text as id, coalesce(array_agg(s.notebook_id::text) "
                "filter (where s.notebook_id is not null), '{}') as notebook_ids "
                "from library_sources l left join sources s on s.library_source_id = l.id "
                "where l.kind = 'generated' "
                "and l.created_at < now() - make_interval(secs => %s) "
                "and not exists (select 1 from outputs o where o.source_id = l.id) "
                "group by l.id order by l.id",
                (older_than_s,),
            ).fetchall()
        return [{"id": r["id"], "notebook_ids": list(r["notebook_ids"])} for r in rows]

    def create_judge_job(self, job: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "insert into judge_jobs (id, owner, target, target_id, notebook_id, level) "
                "values (%(id)s, %(owner)s, %(target)s, %(target_id)s, %(notebook_id)s, %(level)s)",
                job,
            )

    def get_judge_job(self, job_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(f"{_JUDGE_JOB_SELECT} where id = %s", (job_id,)).fetchone()
        return _judge_job(row) if row else None

    def latest_judge_job(self, target: str, target_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"{_JUDGE_JOB_SELECT} where target = %s and target_id = %s "
                "order by created_at desc limit 1",
                (target, target_id),
            ).fetchone()
        return _judge_job(row) if row else None

    def claim_judge_job(self, worker_id: str, stale_after_s: int) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                _CLAIM_JUDGE_SQL, {"worker": worker_id, "stale": stale_after_s}
            ).fetchone()
        return self.get_judge_job(row["id"]) if row else None

    def update_judge_job(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - {"status", "phase", "error"}
        if unknown:
            raise ValueError(f"not an updatable judge_jobs column: {sorted(unknown)}")
        if "phase" in fields:
            fields["phase"] = _jsonb(fields["phase"])
        assignments = [f"{name} = %({name})s" for name in fields] + ["claimed_at = now()"]
        if fields.get("status") in ("done", "failed"):
            assignments.append("finished_at = now()")
        with self._pool.connection() as conn:
            conn.execute(
                f"update judge_jobs set {', '.join(assignments)} where id = %(id)s",
                {**fields, "id": job_id},
            )

    def add_judge_attempt(self, job_id: str, record: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update judge_jobs set attempt_log = attempt_log || %s where id = %s",
                (Jsonb([record]), job_id),
            )

    def add_attempt(self, output_id: str, record: dict[str, Any]) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update outputs set attempt_log = attempt_log || %s where id = %s",
                (Jsonb([record]), output_id),
            )

    def find_outputs(self, id_prefix: str, limit: int) -> list[tuple[OutputRow, str]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS}, coalesce(u.email, '') as owner_email {_OUTPUT_FROM} "
                f"left join users u on u.id = {_OUTPUT_OWNER} "
                "where replace(o.id::text, '-', '') like %(prefix)s "
                "order by o.created_at desc limit %(limit)s",
                {"prefix": id_prefix + "%", "limit": limit},
            ).fetchall()
        return [(_to_output(r), str(r["owner_email"])) for r in rows]

    def report_outputs(self, output_ids: list[str] | None) -> list[OutputRow]:
        where = "o.kind = 'report' and o.status = 'ready'"
        params: dict[str, Any] = {}
        if output_ids is not None:
            where += " and o.id = any(%(ids)s::uuid[])"
            params["ids"] = output_ids
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where {where} order by o.created_at",
                params,
            ).fetchall()
        return [_to_output(r) for r in rows]

    def audio_outputs(self, output_ids: list[str] | None) -> list[OutputRow]:
        where = "o.kind = 'audio' and o.status = 'ready' and o.content ? 'key'"
        params: dict[str, Any] = {}
        if output_ids is not None:
            where += " and o.id = any(%(ids)s::uuid[])"
            params["ids"] = output_ids
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where {where} order by o.created_at",
                params,
            ).fetchall()
        return [_to_output(r) for r in rows]

    def delete_output(self, output_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("delete from outputs where id = %s", (output_id,))

    def claim_output(self, worker_id: str, stale_after_s: int) -> OutputRow | None:
        with self._pool.connection() as conn:
            row = conn.execute(_CLAIM_SQL, {"worker": worker_id, "stale": stale_after_s}).fetchone()
        return self.get_output(row["id"]) if row else None

    def claim_output_copy(self, worker_id: str, stale_after_s: int) -> OutputCopy | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                _CLAIM_COPY_SQL, {"worker": worker_id, "stale": stale_after_s}
            ).fetchone()
        if row is None:
            return None
        return OutputCopy(
            target_notebook=row["target_notebook"],
            source_notebook=row["source_notebook"],
            owner=row["owner"],
            source_map=row["source_map"] or {},
            chunk_map=row["chunk_map"] or {},
            attempts=row["attempts"],
        )

    def end_output_copy(self, target_notebook: str, error: str | None, final: bool) -> None:
        with self._pool.connection() as conn:
            if error is None:
                conn.execute(
                    "delete from output_copies where target_notebook = %s", (target_notebook,)
                )
            else:
                conn.execute(
                    "update output_copies set claimed_at = null, claimed_by = null, "
                    "error = case when %s then %s end where target_notebook = %s",
                    (final, error, target_notebook),
                )

    def copied_outputs(self, notebook_id: str) -> set[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select copied_from::text as id from outputs "
                "where notebook_id = %s and copied_from is not null",
                (notebook_id,),
            ).fetchall()
        return {r["id"] for r in rows}

    def copy_output(
        self,
        row: OutputRow,
        output_id: str,
        target_notebook: str,
        content: dict[str, Any] | None,
        options: dict[str, Any],
        provenance: dict[str, Any] | None,
    ) -> bool:
        source_id = _new_id() if row.source_id else None
        with self._pool.connection() as conn, conn.transaction():
            inserted = conn.execute(
                "insert into outputs (id, notebook_id, owner, origin_title, kind, title, "
                "content, status, options, provenance, copied_from) "
                "select %s, n.id, n.owner, n.title, %s, %s, %s, 'ready', %s, %s, %s "
                "from notebooks n where n.id = %s "
                "on conflict (notebook_id, copied_from) where copied_from is not null "
                "do nothing returning id",
                (
                    output_id,
                    row.kind,
                    row.title,
                    _jsonb(content),
                    Jsonb(options),
                    _jsonb(provenance),
                    row.id,
                    target_notebook,
                ),
            ).fetchone()
            if inserted is None:
                return False
            if source_id is not None:
                # the generated row, its link (same id) and its chunks, as indexed
                conn.execute(
                    "insert into library_sources (id, owner, name, kind, status, summary) "
                    "select %s, n.owner, l.name, 'generated', 'ready', l.summary "
                    "from library_sources l, notebooks n where l.id = %s and n.id = %s",
                    (source_id, row.source_id, target_notebook),
                )
                conn.execute(
                    "insert into sources (id, notebook_id, library_source_id) values (%s, %s, %s)",
                    (source_id, target_notebook, source_id),
                )
                conn.execute(
                    "insert into chunks (id, library_source_id, idx, page, text, embedding) "
                    "select gen_random_uuid(), %s, idx, page, text, embedding "
                    "from chunks where library_source_id = %s",
                    (source_id, row.source_id),
                )
                conn.execute(
                    "update outputs set source_id = %s where id = %s", (source_id, output_id)
                )
        return True

    def charged(self, action_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select exists (select 1 from usage where action_id = %s) as charged",
                (action_id,),
            ).fetchone()
        return bool(row and row["charged"])

    def touch_output(self, output_id: str, phase: dict[str, Any] | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update outputs set claimed_at = now(), phase = coalesce(%s, phase) "
                "where id = %s and claimed_by is not null and status = 'processing'",
                (_jsonb(phase), output_id),
            )

    def waiting_outputs(self, older_than_s: int) -> list[OutputRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select {_OUTPUT_COLUMNS} {_OUTPUT_FROM} where o.status = 'waiting' "
                "and o.deleted_at is null "
                "and o.created_at < now() - make_interval(secs => %s) "
                "order by o.created_at, o.id",
                (older_than_s,),
            ).fetchall()
        return [_to_output(r) for r in rows]

    def release_output(self, output_id: str, error: str | None = None) -> None:
        """Give the job back to the queue, keeping the last error for the next attempt."""
        with self._pool.connection() as conn:
            conn.execute(
                "update outputs set claimed_at = null, claimed_by = null, error = %s where id = %s",
                (error, output_id),
            )

    # -- sources and chunks ----------------------------------------------

    def source_states(self, notebook_id: str) -> list[SourceState]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select s.id::text as id, l.kind, l.status, l.id::text as library_id, l.name, "
                "l.error, coalesce(l.checked_at, l.fetched_at, l.created_at) as read_at "
                "from sources s "
                "join library_sources l on l.id = s.library_source_id where s.notebook_id = %s "
                "order by s.created_at, s.id",
                (notebook_id,),
            ).fetchall()
        return [
            SourceState(
                r["id"],
                r["kind"],
                r["status"],
                r["library_id"],
                r["name"] or "",
                r["error"],
                r["read_at"].isoformat() if r["read_at"] else None,
            )
            for r in rows
        ]

    def source_summaries(self, notebook_id: str) -> list[SourceSummary]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select s.id::text as id, l.name, l.kind, l.summary from sources s "
                "join library_sources l on l.id = s.library_source_id "
                "where s.notebook_id = %s and l.status = 'ready' and l.kind <> 'generated' "
                "order by s.created_at, s.id",
                (notebook_id,),
            ).fetchall()
        return [SourceSummary(r["id"], r["name"], r["kind"], r["summary"] or "") for r in rows]

    def notebook_documents(self, notebook_id: str) -> list[NotebookDocument]:
        """The ready sources, uploads and generated, oldest first; a generated
        one carries its output's kind."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select s.id::text as id, l.name, l.kind, o.kind as output_kind from sources s "
                "join library_sources l on l.id = s.library_source_id "
                "left join outputs o on o.source_id = l.id "
                "where s.notebook_id = %s and l.status = 'ready' "
                "order by s.created_at, s.id",
                (notebook_id,),
            ).fetchall()
        return [NotebookDocument(r["id"], r["name"], r["kind"], r["output_kind"]) for r in rows]

    def create_generated_source(self, notebook_id: str, name: str, summary: str) -> str:
        """A hidden library row of kind 'generated' (owned by the notebook's owner,
        no file, never listed in the library) and its link into the notebook,
        in one transaction and under one id."""
        source_id = _new_id()
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "insert into library_sources (id, owner, name, kind, status, summary) "
                "select %s, owner, %s, 'generated', 'processing', %s from notebooks where id = %s",
                (source_id, name, summary, notebook_id),
            )
            conn.execute(
                "insert into sources (id, notebook_id, library_source_id) values (%s, %s, %s)",
                (source_id, notebook_id, source_id),
            )
        return source_id

    def insert_chunks(
        self, source_id: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Chunks of a generated source, on its library row (same id as the link)."""
        if len(chunks) != len(embeddings):
            raise ValueError("one embedding per chunk")
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(
                "insert into chunks (id, library_source_id, idx, page, text, embedding) "
                "values (%s, %s, %s, %s, %s, %s::vector)",
                [
                    (_new_id(), source_id, c.idx, c.page, c.text, _vector_literal(e))
                    for c, e in zip(chunks, embeddings, strict=True)
                ],
            )

    def set_source_status(self, source_id: str, status: str, error: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update library_sources set status = %s, error = %s where id = %s",
                (status, error, source_id),
            )

    def delete_source(self, source_id: str) -> None:
        """Delete a generated source by its library id (an output's
        ``source_id``): the row goes, and with it (cascade) every link and the
        chunks. Uploaded sources are ingest's to delete."""
        with self._pool.connection() as conn:
            conn.execute(
                "delete from library_sources where id = %s and kind = 'generated'", (source_id,)
            )

    # -- credit (core's helpers; usage rows are the only debit) -------------

    def admin_stats(self, stale_after_s: int) -> dict[str, Any]:
        """Counts for the admin overview, one query per group. The jobs split
        uses the worker's stale-claim limit: a ``processing`` row whose claim is
        younger than ``stale_after_s`` is running, an older or missing claim is
        pending again (a worker will take it over)."""
        stale = {"stale": f"{stale_after_s} seconds"}
        with self._pool.connection() as conn:
            notebooks = conn.execute("select count(*) as total from notebooks").fetchone()
            messages = conn.execute(
                "select count(*) as total, "
                "count(*) filter (where created_at > now() - interval '24 hours') as last_24h "
                "from messages"
            ).fetchone()
            outputs = conn.execute(
                "select kind, status, count(*) as n from outputs group by kind, status"
            ).fetchall()
            jobs = conn.execute(
                "select count(*) filter (where status = 'waiting' or (status = 'processing' "
                "and (claimed_at is null or claimed_at < now() - %(stale)s::interval))) "
                "as pending, "
                "count(*) filter (where status = 'processing' "
                "and claimed_at >= now() - %(stale)s::interval) as running, "
                "count(*) filter (where status = 'failed') as failed from outputs",
                stale,
            ).fetchone()
            shared = conn.execute(
                "select count(*) as outputs from outputs where share_token is not null"
            ).fetchone()
        return {
            "notebooks": notebooks,
            "messages": messages,
            "outputs": [(r["kind"], r["status"], r["n"]) for r in outputs],
            "jobs": jobs,
            "shared": shared,
        }

    def get_chunk(self, chunk_id: str, user_id: str) -> dict[str, Any] | None:
        """The chunk with its position and source, if its library source belongs
        to ``user_id`` and is linked into one of their notebooks; the source id
        is that link's (the oldest, when the file is in several notebooks)."""
        with self._pool.connection() as conn:
            row = conn.execute(_CHUNK_SQL, {"chunk_id": chunk_id, "user_id": user_id}).fetchone()
        return dict(row) if row else None

    def daily_stats(self, days: int) -> list[dict[str, Any]]:
        """Per UTC day, the last ``days`` days up to today: messages written and
        outputs created by kind, in one query; days without activity included."""
        with self._pool.connection() as conn:
            rows = conn.execute(_DAILY_SQL, {"days": days}).fetchall()
        return [dict(r) for r in rows]

    def has_credit(self, user_id: str) -> bool:
        with self._pool.connection() as conn:
            return has_credit(core_connection(conn), uuid.UUID(user_id))

    def balance_cents(self, user_id: str) -> Decimal:
        with self._pool.connection() as conn:
            return balance_cents(core_connection(conn), uuid.UUID(user_id))

    def held_cents(self, user_id: str) -> Decimal:
        with self._pool.connection() as conn:
            row = conn.execute(_HELD_SQL, {"owner": user_id}).fetchone()
        return Decimal(str(row["held"])) if row else Decimal(0)

    def user_output_contents(self, user_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                f"select o.content {_OUTPUT_FROM} where o.content is not null "
                f"and {_OUTPUT_OWNER} = %(owner)s",
                {"owner": user_id},
            ).fetchall()
        return [row["content"] for row in rows]

    def delete_user_data(self, user_id: str) -> None:
        """The user's generated library rows (links and chunks cascade) and
        outputs, wherever their origin, and the messages and conversations of
        the user's notebooks, in one transaction. The notebooks and the
        uploads are ingest's to delete."""
        owner = {"owner": user_id}
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "delete from library_sources where owner = %(owner)s and kind = 'generated'", owner
            )
            conn.execute(
                "delete from outputs o using notebooks n where o.owner is null "
                "and n.id = o.notebook_id and n.owner = %(owner)s",
                owner,
            )
            conn.execute("delete from outputs where owner = %(owner)s", owner)
            conn.execute("delete from judge_jobs where owner = %(owner)s", owner)
            for table in ("messages", "conversations"):
                conn.execute(f"delete from {table} where notebook_id in ({_USER_NOTEBOOKS})", owner)

    def admin_role(self, user_id: str) -> Role:
        with self._pool.connection() as conn:
            return admin_role(core_connection(conn), uuid.UUID(user_id))

    def pricing_rules(self) -> PricingRules:
        with self._pool.connection() as conn:
            return self._rules.current(core_connection(conn))

    def record_usage(self, booking: Booking, usage: Usage) -> None:
        with self._pool.connection() as conn:
            core = core_connection(conn)
            record_usage(
                core,
                uuid.UUID(booking.user_id),
                uuid.UUID(booking.notebook_id) if booking.notebook_id else None,
                SERVICE_NAME,
                booking.action,
                booking.action_id,
                usage,
                prices=self._prices,
                rules=self._rules.current(core),
            )


class _TupleRows:
    """Core's helpers read rows by position; this service's pool hands out dict
    rows. Core only needs ``cursor()``, so hand it one that yields tuples."""

    def __init__(self, conn: Connection[DictRow]) -> None:
        self._conn = conn

    def cursor(self) -> Cursor[TupleRow]:
        return self._conn.cursor(row_factory=tuple_row)


def core_connection(conn: Connection[DictRow]) -> CoreConnection:
    return _TupleRows(conn)


@contextmanager
def core_connect(pool: Pool) -> Iterator[CoreConnection]:
    """A zero-argument connection factory over core's protocol (rate-limit store)."""
    with pool.connection() as conn:
        yield core_connection(conn)


def make_pool(database_url: str) -> Pool:
    """Autocommit connections: every method above is one statement or one
    executemany, so there is nothing to group into a transaction."""
    return ConnectionPool(
        database_url,
        connection_class=Connection[DictRow],
        min_size=1,
        max_size=4,
        kwargs={"row_factory": dict_row, "autocommit": True},
        open=True,
    )


def _new_id() -> str:
    return str(uuid.uuid4())


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _jsonb(value: Any) -> Any:
    return Jsonb(value) if value is not None else None


def _to_message(row: dict[str, Any]) -> Message:
    support = row.get("support") or {}
    fields = {k: v for k, v in row.items() if k != "support"}
    return Message.model_validate(
        {
            **fields,
            "citations": row.get("citations") or [],
            "units": support.get("units"),
            "check": support.get("check"),
            "web_pages": support.get("web_pages") or [],
        }
    )


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _to_output(row: dict[str, Any]) -> OutputRow:
    return OutputRow(
        id=row["id"],
        notebook_id=row["notebook_id"],
        owner=row["owner"],
        kind=row["kind"],
        title=row["title"],
        content=row["content"],
        status=row["status"],
        error=row["error"],
        share_token=row["share_token"],
        source_id=row["source_id"],
        attempts=int(row.get("attempts", 0)),
        created_at=str(row["created_at"]),
        options=row.get("options") or {},
        origin_title=row.get("origin_title") or "",
        deleted_at=_str_or_none(row.get("deleted_at")),
        purge_at=_str_or_none(row.get("purge_at")),
        provenance=row.get("provenance"),
        booking_id=row.get("booking_id"),
        phase=row.get("phase"),
        attempt_log=list(row.get("attempt_log") or []),
        finished_at=_str_or_none(row.get("finished_at")),
    )
