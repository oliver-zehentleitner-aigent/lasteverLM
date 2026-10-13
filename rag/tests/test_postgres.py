"""The SQL paths of the store against a real PostgreSQL with pgvector: credit
through core's helpers over this service's dict-row pool, messages, the
outputs queue (claim, release, stale takeover, attempts), generated sources
with their chunks, scoped vector search, and the admin counts. Everything else in the suite
runs against fakes; this file is what `make test-postgres` runs against a
throwaway container and skips without `RAG_TEST_DATABASE_URL`.

The database starts empty. The migrations of infra (extension), core
(usage), account (users, ledger) and ingest (notebooks, sources, chunks)
are applied from the repository as rag's own is; ingest's psql variable
for the vector dimension is substituted here, since there is no psql.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from lasteverlm_core import (
    Chunk,
    PostgresRateLimitStore,
    RateLimiter,
    RateLimitSettings,
    Usage,
    balance_cents,
    parse_model_prices,
)

from lasteverlm_rag.store import (
    PgVectorRetriever,
    PostgresStore,
    core_connect,
    core_connection,
    make_pool,
)

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("RAG_TEST_DATABASE_URL")
REPO = Path(__file__).resolve().parents[2]
DIMENSION = 3
PRICES = parse_model_prices(
    '{"llm": {"in": 100, "out": 300}, "emb": {"in": 10, "out": 0}, "tts": {"in": 2000, "out": 0}}'
)

MIGRATION_DIRS = ["infra", "core", "account", "ingest", "rag"]

# History written before conversations existed, inserted right after rag's
# 0001 so that 0002's backfill runs over it.
LEGACY_USER, LEGACY_NOTEBOOK = str(uuid4()), str(uuid4())
LEGACY_SEED = f"""
insert into users (id, email) values ('{LEGACY_USER}', 'legacy@test.local');
insert into notebooks (id, owner, title) values ('{LEGACY_NOTEBOOK}', '{LEGACY_USER}', 'old');
insert into messages (id, notebook_id, role, content, created_at) values
    ('{uuid4()}', '{LEGACY_NOTEBOOK}', 'user', 'old question', now() - interval '2 days'),
    ('{uuid4()}', '{LEGACY_NOTEBOOK}', 'assistant', 'old answer', now() - interval '1 day');
"""


def _sql(path: Path) -> str:
    """A migration as psycopg can run it: psql meta-commands dropped, the
    dimension variable substituted (infra's runner passes it to psql)."""
    text = re.sub(r"^\\.*$", "", path.read_text(), flags=re.MULTILINE)
    return text.replace(":EMBEDDING_DIMENSION", str(DIMENSION))


@pytest.fixture(scope="module")
def database_url() -> str:
    if not DATABASE_URL:
        pytest.skip("RAG_TEST_DATABASE_URL not set")
    for _ in range(60):
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
                for service in MIGRATION_DIRS:
                    for path in sorted((REPO / service / "db" / "migrations").glob("*.sql")):
                        conn.execute(_sql(path))
                        if (service, path.name) == ("rag", "0001_rag.sql"):
                            conn.execute(LEGACY_SEED)
                conn.commit()
            return DATABASE_URL
        except psycopg.OperationalError:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not come up")


@pytest.fixture
def pool(database_url: str) -> Iterator:
    pool = make_pool(database_url)
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture
def store(pool) -> PostgresStore:
    return PostgresStore(pool, PRICES)


@pytest.fixture
def user(pool) -> str:
    user_id = str(uuid4())
    with pool.connection() as conn:
        conn.execute(
            "insert into users (id, email) values (%s, %s)", (user_id, f"{user_id}@test.local")
        )
        conn.execute(
            "insert into ledger (user_id, amount_cents, reason) values (%s, 1000, 'seed')",
            (user_id,),
        )
    return user_id


@pytest.fixture
def notebook(pool, user: str) -> str:
    notebook_id = str(uuid4())
    with pool.connection() as conn:
        conn.execute(
            "insert into notebooks (id, owner, title) values (%s, %s, 'nb')", (notebook_id, user)
        )
    return notebook_id


def add_source(
    pool, notebook_id: str, status: str, kind: str = "pdf", library_id: str | None = None
) -> str:
    """Link a library source into the notebook the way ingest does; a new
    library row (owned by the notebook's owner) unless ``library_id`` is given.
    Returns the link id, the public source id."""
    source_id = str(uuid4())
    with pool.connection() as conn:
        if library_id is None:
            library_id = str(uuid4())
            conn.execute(
                "insert into library_sources (id, owner, name, kind, status, summary) "
                "select %s, owner, 's', %s, %s, 'summary' from notebooks where id = %s",
                (library_id, kind, status, notebook_id),
            )
        conn.execute(
            "insert into sources (id, notebook_id, library_source_id) values (%s, %s, %s)",
            (source_id, notebook_id, library_id),
        )
    return source_id


def library_id_of(pool, source_id: str) -> str:
    with pool.connection() as conn:
        row = conn.execute(
            "select library_source_id::text as id from sources where id = %s", (source_id,)
        ).fetchone()
    return str(row["id"])


# -- credit through core over the dict-row pool ----------------------------------


def test_credit_admin_and_usage_over_dict_row_pool(store, pool, user, notebook):
    def balance() -> int:
        with pool.connection() as conn:
            return balance_cents(core_connection(conn), UUID(user))

    assert store.has_credit(user) and not store.is_admin(user)
    store.record_usage(user, notebook, Usage("llm", "llm", 500_000, 100_000))  # 50 + 30 = 80
    store.record_usage(user, None, Usage("embedding", "emb", 1, 0))  # ceil(0.00001) = 1
    store.record_usage(user, notebook, Usage("tts", "tts", 1500, 0))  # 1500 chars: 3
    assert balance() == 1000 - 84
    store.record_usage(user, None, Usage("llm", "llm", 10_000_000, 0))  # 1000: below zero
    assert not store.has_credit(user)
    with pool.connection() as conn:
        conn.execute("update users set is_admin = true where id = %s", (user,))
    assert store.is_admin(user) and not store.has_credit(user)  # admins need credit too
    assert not store.is_admin(str(uuid4()))  # no users row: not an admin
    assert store.get_notebook(notebook) == {"id": notebook, "owner": user, "title": "nb"}


def test_rate_limit_store_over_the_core_connection(pool):
    limiter = RateLimiter(
        PostgresRateLimitStore(partial(core_connect, pool)), RateLimitSettings(per_minute=1)
    )
    now = datetime.now(UTC)
    ip = f"10.0.{uuid4().int % 256}.{uuid4().int % 256}"

    async def two_requests() -> list[str]:
        first = await limiter.check(ip, now)
        await limiter.record(_entry(ip, now))
        second = await limiter.check(ip, now)
        return [first.kind, second.kind]

    assert asyncio.run(two_requests()) == ["allowed", "blocked"]


def _entry(ip: str, now: datetime):
    from lasteverlm_core import AccessLogEntry

    return AccessLogEntry(
        at=now, ip=ip, path="/x", method="GET", status=200, user_id=None, service="rag"
    )


# -- messages ----------------------------------------------------------------------


def test_messages_round_trip_with_citations(store, notebook):
    citation = {
        "n": 1,
        "source_id": str(uuid4()),
        "source_name": "a.pdf",
        "source_kind": "pdf",
        "chunk_id": str(uuid4()),
        "page": 2,
        "quote": "q",
    }
    chat = store.create_conversation(notebook, "Chat 1")
    store.insert_message(notebook, chat.id, "user", "question", None)
    stored = store.insert_message(notebook, chat.id, "assistant", "answer [1]", [citation])
    messages = store.list_messages(chat.id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].citations == []
    assert (
        str(messages[1].id) == stored.id
        if isinstance(stored.id, str)
        else messages[1].id == stored.id
    )
    assert str(messages[1].citations[0].chunk_id) == citation["chunk_id"]
    assert messages[1].citations[0].page == 2


# -- the outputs queue -------------------------------------------------------------


def test_claim_waits_for_sources_counts_attempts_and_takes_over_stale_claims(store, pool, notebook):
    pending = add_source(pool, notebook, "processing")
    add_source(pool, notebook, "processing", kind="generated")  # never blocks a claim
    row = store.create_output(notebook, "report", "waiting")
    assert (row.status, row.attempts, row.title) == ("waiting", 0, "")

    assert store.claim_output("w1", stale_after_s=600) is None  # an upload is still processing

    with pool.connection() as conn:
        conn.execute(
            "update library_sources set status = 'ready' where id = %s",
            (library_id_of(pool, pending),),
        )
    job = store.claim_output("w1", stale_after_s=600)
    assert job is not None and (job.id, job.attempts, job.owner) == (row.id, 1, row.owner)
    assert store.claim_output("w2", stale_after_s=600) is None  # held by w1

    store.release_output(job.id, error="transient")
    again = store.claim_output("w2", stale_after_s=600)
    assert again is not None and (again.attempts, again.error) == (2, "transient")

    with pool.connection() as conn:  # w2 died: its claim is older than the stale limit
        conn.execute(
            "update outputs set claimed_at = now() - interval '11 minutes' where id = %s", (job.id,)
        )
    stale = store.claim_output("w3", stale_after_s=600)
    assert stale is not None and stale.attempts == 3
    with pool.connection() as conn:
        claimed_by = conn.execute(
            "select claimed_by from outputs where id = %s", (job.id,)
        ).fetchone()["claimed_by"]
    assert claimed_by == "w3"

    store.update_output(job.id, status="ready", title="T", content={"markdown": "# x"}, error=None)
    done = store.get_output(job.id)
    assert done is not None and (done.status, done.content) == ("ready", {"markdown": "# x"})
    assert store.claim_output("w4", stale_after_s=600) is None  # ready rows are not jobs
    assert [o.id for o in store.list_outputs(notebook)] == [job.id]


def test_share_token_and_delete(store, notebook, pool):
    row = store.create_output(notebook, "quiz", "processing")
    store.update_output(row.id, share_token="tok-" + row.id, status="ready")
    shared = store.get_shared_output("tok-" + row.id)
    assert shared is not None and shared.id == row.id
    with pytest.raises(ValueError):
        store.update_output(row.id, status="ready", owner="x")  # not an updatable column
    store.update_output(row.id, share_token=None)
    assert store.get_shared_output("tok-" + row.id) is None
    store.delete_output(row.id)
    assert store.get_output(row.id) is None


# -- generated sources, chunks, vector search -------------------------------------


def test_generated_source_chunks_and_scoped_search(store, pool, notebook):
    retriever = PgVectorRetriever(pool)
    upload = add_source(pool, notebook, "ready")
    with pool.connection() as conn:
        conn.execute(
            "insert into chunks (id, library_source_id, idx, page, text, embedding) "
            "values (%s, %s, 0, 3, 'upload chunk', '[1,0,0]')",
            (str(uuid4()), library_id_of(pool, upload)),
        )
    generated = store.create_generated_source(notebook, "Report", "summary")
    store.insert_chunks(
        generated,
        [Chunk(0, None, "generated near"), Chunk(1, None, "generated far")],
        [[0.9, 0.1, 0.0], [0.0, 0.0, 1.0]],
    )
    assert store.source_states(notebook)[-1].status == "processing"
    # only ready uploads feed the generators, never generated sources
    assert [s.source_id for s in store.source_summaries(notebook)] == [upload]

    # the generated source is still processing: only the upload's chunk is searchable
    before = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0)
    assert [h.text for h in before] == ["upload chunk"]
    store.set_source_status(generated, "ready")

    # unscoped: the uploads, or with ``generated`` the generated documents only
    assert [h.text for h in retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0)] == [
        "upload chunk"
    ]
    hits = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0, generated=True)
    assert [(h.text, h.source_kind, h.page) for h in hits] == [
        ("generated near", "generated", None),
        ("generated far", "generated", None),
    ]
    assert hits[-1].similarity == pytest.approx(0.0)
    floored = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.5, generated=True)
    assert [h.text for h in floored] == ["generated near"]

    # the chat's document list: both, the generated one with its output's kind
    output = store.create_output(notebook, "mindmap", "processing")
    store.update_output(output.id, status="ready", source_id=generated)
    assert [(d.name, d.kind, d.output_kind) for d in store.notebook_documents(notebook)] == [
        ("s", "pdf", None),
        ("Report", "generated", "mindmap"),
    ]
    scoped = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0, source_id=generated)
    assert [h.text for h in scoped] == ["generated near", "generated far"]
    assert retriever.search(str(uuid4()), [1.0, 0.0, 0.0], k=8, floor=0.0) == []

    store.delete_source(generated)
    with pool.connection() as conn:
        left = conn.execute(
            "select (select count(*) from chunks where library_source_id = %(id)s) "
            "+ (select count(*) from sources where id = %(id)s) "
            "+ (select count(*) from library_sources where id = %(id)s) as n",
            {"id": generated},
        )
        assert left.fetchone()["n"] == 0
    store.delete_source(upload)  # an upload is ingest's to delete: untouched
    assert [s.source_id for s in store.source_summaries(notebook)] == [upload]


def test_a_library_source_linked_into_two_notebooks_is_searched_from_both(store, pool, user):
    retriever = PgVectorRetriever(pool)
    notebooks = []
    for title in ("first", "second"):
        notebook_id = str(uuid4())
        with pool.connection() as conn:
            conn.execute(
                "insert into notebooks (id, owner, title) values (%s, %s, %s)",
                (notebook_id, user, title),
            )
        notebooks.append(notebook_id)
    first = add_source(pool, notebooks[0], "ready")
    library = library_id_of(pool, first)
    second = add_source(pool, notebooks[1], "ready", library_id=library)
    with pool.connection() as conn:
        conn.execute(
            "insert into chunks (id, library_source_id, idx, text, embedding) "
            "values (%s, %s, 0, 'shared chunk', '[0,1,0]')",
            (str(uuid4()), library),
        )
    hits = [retriever.search(nb, [0.0, 1.0, 0.0], k=8, floor=0.0) for nb in notebooks]
    # one chunk, cited under the link id each notebook knows
    assert [(h[0].text, h[0].source_id) for h in hits] == [
        ("shared chunk", first),
        ("shared chunk", second),
    ]
    assert hits[0][0].chunk_id == hits[1][0].chunk_id
    # a notebook whose linked library source is still processing holds back its outputs
    with pool.connection() as conn:
        conn.execute("update library_sources set status = 'processing' where id = %s", (library,))
    assert [s.status for s in store.source_states(notebooks[1])] == ["processing"]
    assert retriever.search(notebooks[1], [0.0, 1.0, 0.0], k=8, floor=0.0) == []


def test_admin_stats_counts_across_users(store, pool, notebook):
    before = store.admin_stats(600)
    running = store.create_output(notebook, "quiz", "processing")
    stale = store.create_output(notebook, "audio", "processing")
    store.create_output(notebook, "report", "waiting")
    shared = store.create_output(notebook, "table", "failed")
    store.update_output(shared.id, share_token=f"t-{shared.id}")
    chat = store.create_conversation(notebook, "Chat 1")
    store.insert_message(notebook, chat.id, "user", "hi", [])
    with pool.connection() as conn:
        conn.execute(
            "update outputs set claimed_at = now(), claimed_by = 'w' where id = %s", (running.id,)
        )
        conn.execute(
            "update outputs set claimed_at = now() - interval '11 minutes', claimed_by = 'w' "
            "where id = %s",
            (stale.id,),
        )
    after = store.admin_stats(600)

    def delta(group: str, key: str) -> int:
        return int(after[group][key]) - int(before[group][key])

    assert delta("messages", "total") == delta("messages", "last_24h") == 1
    assert (delta("jobs", "pending"), delta("jobs", "running"), delta("jobs", "failed")) == (
        2,
        1,
        1,
    )
    assert delta("shared", "outputs") == 1
    assert after["notebooks"]["total"] >= 1

    def count(stats: dict[str, Any], kind: str, status: str) -> int:
        return sum(n for k, s, n in stats["outputs"] if (k, s) == (kind, status))

    assert count(after, "audio", "processing") - count(before, "audio", "processing") == 1
    assert count(after, "table", "failed") - count(before, "table", "failed") == 1


def test_migration_moves_existing_history_into_chat_1(store, pool):
    (chat,) = store.list_conversations(LEGACY_NOTEBOOK)
    assert (chat.title, chat.owner) == ("Chat 1", LEGACY_USER)
    assert [m.content for m in store.list_messages(chat.id)] == ["old question", "old answer"]
    with pool.connection() as conn:
        first = conn.execute(
            "select min(created_at) as t from messages where notebook_id = %s", (LEGACY_NOTEBOOK,)
        ).fetchone()["t"]
    assert chat.created_at == first


def test_conversations_history_window_and_cascade(store, pool, notebook):
    chat = store.create_conversation(notebook, "Chat 2")
    other = store.create_conversation(notebook, "Notes")
    for i in range(5):
        store.insert_message(notebook, chat.id, "user", f"m{i}", None)
    store.insert_message(notebook, other.id, "user", "elsewhere", None)
    assert [c.title for c in store.list_conversations(notebook)] == ["Chat 2", "Notes"]
    assert store.rename_conversation(other.id, "Setup").title == "Setup"
    assert [c.title for c in store.list_conversations(notebook)] == ["Chat 2", "Setup"]
    assert (store.get_conversation(chat.id) or chat).notebook_id == notebook
    assert [m.content for m in store.list_messages(chat.id, last=2)] == ["m3", "m4"]
    assert len(store.list_messages(chat.id)) == 5

    store.delete_conversation(chat.id)
    assert store.get_conversation(chat.id) is None
    with pool.connection() as conn:
        left = conn.execute(
            "select count(*) as n from messages where conversation_id = %s", (chat.id,)
        ).fetchone()["n"]
    assert left == 0
    assert [m.content for m in store.list_messages(other.id)] == ["elsewhere"]


def test_daily_stats_count_per_utc_day(store, pool, notebook):
    chat = store.create_conversation(notebook, "Chat 1")
    before = {r["day"]: r for r in store.daily_stats(3)}
    store.insert_message(notebook, chat.id, "user", "today", None)
    old = store.insert_message(notebook, chat.id, "user", "two days ago", None)
    store.create_output(notebook, "report", "ready")
    store.create_output(notebook, "audio", "failed")
    gone = store.create_output(notebook, "quiz", "ready")
    with pool.connection() as conn:
        conn.execute(
            "update messages set created_at = now() - interval '2 days' where id = %s", (old.id,)
        )
        conn.execute(
            "update outputs set created_at = now() - interval '40 days' where id = %s", (gone.id,)
        )
    rows = store.daily_stats(3)
    assert len(rows) == 3 and rows[0]["day"] < rows[1]["day"] < rows[2]["day"]
    today, first = rows[2], rows[0]

    def kinds(row: dict[str, Any]) -> dict[str, int]:
        return {k: int(v) for k, v in row["by_kind"].items()}

    def gained(row: dict[str, Any], kind: str) -> int:
        return kinds(row).get(kind, 0) - kinds(before[row["day"]]).get(kind, 0)

    assert today["messages"] - before[today["day"]]["messages"] == 1
    assert first["messages"] - before[first["day"]]["messages"] == 1
    assert (gained(today, "report"), gained(today, "audio"), gained(today, "quiz")) == (1, 1, 0)


def test_search_and_chunk_view_carry_the_position_in_the_source(store, pool, user, notebook):
    retriever = PgVectorRetriever(pool)
    upload = add_source(pool, notebook, "ready")
    library = library_id_of(pool, upload)
    ids = [str(uuid4()) for _ in range(3)]
    with pool.connection() as conn:
        for idx, (chunk_id, vector) in enumerate(
            zip(ids, ("[1,0,0]", "[0,1,0]", "[0,0,1]"), strict=True)
        ):
            conn.execute(
                "insert into chunks (id, library_source_id, idx, page, text, embedding) "
                "values (%s, %s, %s, %s, %s, %s)",
                (chunk_id, library, idx, idx + 1, f" text {idx}\n", vector),
            )
    (hit,) = retriever.search(notebook, [0.0, 1.0, 0.0], k=1, floor=0.0)
    assert (hit.chunk_id, hit.chunk_index, hit.chunk_count) == (ids[1], 1, 3)

    view = store.get_chunk(ids[1], user)
    assert view is not None
    assert (view["source_id"], view["chunk_index"], view["chunk_count"], view["page"]) == (
        upload,
        1,
        3,
        2,
    )
    assert view["text"] == " text 1\n"  # verbatim
    assert store.get_chunk(ids[1], str(uuid4())) is None  # not the owner
    assert store.get_chunk(str(uuid4()), user) is None


def test_output_options_round_trip(store, notebook):
    chosen = {"language": "de", "voice": "serena", "speed": 1.25}
    row = store.create_output(notebook, "audio", "processing", chosen)
    assert row.options == chosen
    assert (store.get_output(row.id) or row).options == chosen
    assert store.create_output(notebook, "report", "processing").options == {}
