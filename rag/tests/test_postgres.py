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


def add_source(pool, notebook_id: str, status: str, kind: str = "pdf") -> str:
    source_id = str(uuid4())
    with pool.connection() as conn:
        conn.execute(
            "insert into sources (id, notebook_id, name, kind, status, summary) "
            "values (%s, %s, 's', %s, %s, 'summary')",
            (source_id, notebook_id, kind, status),
        )
    return source_id


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
    assert store.is_admin(user) and store.has_credit(user)  # admins have unlimited credit
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
    store.insert_message(notebook, "user", "question", None)
    stored = store.insert_message(notebook, "assistant", "answer [1]", [citation])
    messages = store.list_messages(notebook)
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
        conn.execute("update sources set status = 'ready' where id = %s", (pending,))
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
            "insert into chunks (id, source_id, notebook_id, idx, page, text, embedding) "
            "values (%s, %s, %s, 0, 3, 'upload chunk', '[1,0,0]')",
            (str(uuid4()), upload, notebook),
        )
    generated = store.create_generated_source(notebook, "Report", "summary")
    store.insert_chunks(
        generated,
        notebook,
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

    # unscoped: uploads only by default; generated documents on request
    assert [h.text for h in retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0)] == [
        "upload chunk"
    ]
    hits = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0, include_generated=True)
    assert [(h.text, h.source_kind, h.page) for h in hits][:2] == [
        ("upload chunk", "pdf", 3),
        ("generated near", "generated", None),
    ]
    assert hits[0].similarity == pytest.approx(1.0) and hits[-1].similarity == pytest.approx(0.0)
    floored = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.5, include_generated=True)
    assert [h.text for h in floored] == ["upload chunk", "generated near"]
    scoped = retriever.search(notebook, [1.0, 0.0, 0.0], k=8, floor=0.0, source_id=generated)
    assert [h.text for h in scoped] == ["generated near", "generated far"]
    assert retriever.search(str(uuid4()), [1.0, 0.0, 0.0], k=8, floor=0.0) == []

    store.delete_source(generated)
    with pool.connection() as conn:
        left = conn.execute("select count(*) as n from chunks where source_id = %s", (generated,))
        assert left.fetchone()["n"] == 0


def test_admin_stats_counts_across_users(store, pool, notebook):
    before = store.admin_stats(600)
    running = store.create_output(notebook, "quiz", "processing")
    stale = store.create_output(notebook, "audio", "processing")
    store.create_output(notebook, "report", "waiting")
    shared = store.create_output(notebook, "table", "failed")
    store.update_output(shared.id, share_token=f"t-{shared.id}")
    store.insert_message(notebook, "user", "hi", [])
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
