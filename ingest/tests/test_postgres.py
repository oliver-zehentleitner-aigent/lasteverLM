"""The SQL paths of the repository against a real PostgreSQL with pgvector:
the library and its dedupe conflict, ownership on every owner-scoped call,
the trash with the owner's retention, the queue (generated, trashed and
backed-off rows, stale takeover, concurrent claims), the seed claim and the
admin counts. Everything else in the suite runs against fakes; this file is
what `make test-postgres` runs against a throwaway container and skips
without `INGEST_TEST_DATABASE_URL`.

The database starts empty. The migrations of infra (extension), core
(usage), account (users, ledger, preferences) and ingest are applied from
the repository; ingest's psql conditional for the vector dimension is
replaced here, since there is no psql.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from lasteverlm_core import Chunk, parse_model_prices

from lasteverlm_ingest.repository import NewLibrarySource, PostgresRepository

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("INGEST_TEST_DATABASE_URL")
REPO = Path(__file__).resolve().parents[2]
DIMENSION = 3
PRICES = parse_model_prices('{"llm": {"in": 100, "out": 300}, "emb": {"in": 10, "out": 0}}')
MIGRATION_DIRS = ["infra", "core", "account", "ingest"]
STALE = 600


def _sql(path: Path) -> str:
    """A migration as psycopg can run it: psql meta-commands dropped, the
    dimension variable substituted (infra's runner passes it to psql)."""
    text = re.sub(r"^\\.*$", "", path.read_text(), flags=re.MULTILINE)
    return text.replace(":EMBEDDING_DIMENSION", str(DIMENSION))


@pytest.fixture(scope="module")
def database_url() -> str:
    if not DATABASE_URL:
        pytest.skip("INGEST_TEST_DATABASE_URL not set")
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


@pytest.fixture(scope="module")
def repo(database_url: str) -> Iterator[PostgresRepository]:
    repository = PostgresRepository(database_url, model_prices=PRICES)
    try:
        yield repository
    finally:
        repository.close()


def _execute(repo: PostgresRepository, sql: str, params: tuple = ()) -> None:
    with repo.connection() as conn:
        conn.execute(sql, params)


def _user(repo: PostgresRepository, preferences: str = "{}", cents: int = 1000) -> UUID:
    user = uuid4()
    _execute(
        repo,
        "insert into users (id, email, preferences) values (%s, %s, %s::jsonb)",
        (user, f"{user}@test.local", preferences),
    )
    if cents:
        _execute(
            repo,
            "insert into ledger (user_id, amount_cents, reason) values (%s, %s, 'seed')",
            (user, cents),
        )
    return user


def _library(repo: PostgresRepository, owner: UUID, key: str | None = None, **fields):
    library_id = uuid4()
    return repo.create_library_source(
        NewLibrarySource(
            id=library_id,
            owner=owner,
            name=fields.pop("name", "notes.txt"),
            kind=fields.pop("kind", "text"),
            dedupe_key=key or f"sha256:{library_id.hex}",
            url=None,
            size_bytes=10,
            storage_path=f"{owner}/{library_id}/notes.txt",
            **fields,
        )
    )


def _generated(repo: PostgresRepository, notebook_id: UUID, owner: UUID) -> UUID:
    """A rag output, the way rag writes it: a generated library row and its link."""
    library_id = uuid4()
    _execute(
        repo,
        "insert into library_sources (id, owner, name, kind, status) "
        "values (%s, %s, 'Report', 'generated', 'processing')",
        (library_id, owner),
    )
    _execute(
        repo,
        "insert into sources (id, notebook_id, library_source_id) values (%s, %s, %s)",
        (uuid4(), notebook_id, library_id),
    )
    return library_id


def _claim_all(repo: PostgresRepository, stale: int = STALE) -> set[UUID]:
    claimed = set()
    while (library_id := repo.claim_library_source("test", stale)) is not None:
        claimed.add(library_id)
    return claimed


def test_dedupe_conflict_returns_the_existing_row_also_from_the_trash(repo):
    owner, other = _user(repo), _user(repo)
    first = _library(repo, owner, "sha256:same")
    again = _library(repo, owner, "sha256:same", name="copy.txt")
    assert again.id == first.id and again.name == "notes.txt"
    # Dedupe keys are per owner: the same bytes from another user are their own.
    assert _library(repo, other, "sha256:same").id != first.id
    assert repo.trash_library_source(owner, first.id)
    found = repo.find_library_source(owner, "sha256:same")
    assert found is not None and found.id == first.id and found.deleted_at is not None


def test_owner_scoped_calls_refuse_a_foreign_owner(repo):
    owner, stranger = _user(repo), _user(repo)
    notebook = repo.create_notebook(owner, "mine")
    entry = _library(repo, owner)
    repo.link_source(notebook.id, entry.id)

    assert repo.get_notebook(stranger, notebook.id) is None
    assert repo.list_notebooks(stranger) == []
    assert repo.get_library_entry(stranger, entry.id) is None
    assert repo.list_library(stranger) == []
    assert repo.find_library_source(stranger, entry.dedupe_key or "") is None
    assert not repo.trash_library_source(stranger, entry.id)
    assert repo.trash_library_source(owner, entry.id)
    assert repo.list_trash(stranger) == []
    assert not repo.restore_library_source(stranger, entry.id)
    assert repo.purge_library_source(stranger, entry.id) == (False, None)
    repo.delete_notebook(stranger, notebook.id)
    assert repo.get_notebook(owner, notebook.id) is not None


def test_library_entry_lists_its_notebooks_and_storage_path(repo):
    owner = _user(repo)
    a, b = repo.create_notebook(owner, "A"), repo.create_notebook(owner, "B")
    entry = _library(repo, owner)
    link_a, new = repo.link_source(a.id, entry.id)
    assert new
    again, new = repo.link_source(a.id, entry.id)
    assert not new and again.id == link_a.id
    link_b, _ = repo.link_source(b.id, entry.id)
    listed = repo.get_library_entry(owner, entry.id)
    assert listed is not None and listed.storage_path == entry.storage_path
    assert [(n.title, n.source_id) for n in listed.notebooks] == [
        ("A", link_a.id),
        ("B", link_b.id),
    ]
    assert repo.first_notebook(entry.id) == a.id
    repo.detach_source(link_a.id)
    assert [n.title for n in repo.list_library(owner)[0].notebooks] == ["B"]


def test_deleting_a_notebook_keeps_its_library_and_drops_its_outputs(repo):
    owner = _user(repo)
    notebook = repo.create_notebook(owner, "nb")
    entry = _library(repo, owner)
    repo.link_source(notebook.id, entry.id)
    output = _generated(repo, notebook.id, owner)
    assert [e.id for e in repo.list_library(owner)] == [entry.id]
    repo.delete_notebook(owner, notebook.id)
    assert repo.get_library_source(output) is None
    assert repo.get_library_entry(owner, entry.id) is not None


def test_trash_retention_follows_the_owners_preference(repo):
    default, short, junk = (
        _user(repo),
        _user(repo, '{"trash_days": 3}'),
        _user(repo, '{"trash_days": "x"}'),
    )
    for owner, days in ((default, 14), (short, 3), (junk, 14)):
        entry = _library(repo, owner)
        assert repo.trash_library_source(owner, entry.id)
        assert repo.get_library_entry(owner, entry.id) is None
        [trashed] = repo.list_trash(owner)
        assert trashed.id == entry.id
        assert (trashed.purge_at - trashed.deleted_at).days == days


def test_restore_and_purge(repo):
    owner = _user(repo)
    entry = _library(repo, owner)
    assert not repo.restore_library_source(owner, entry.id)  # not in the trash
    assert repo.purge_library_source(owner, entry.id) == (False, None)  # not in the trash
    repo.trash_library_source(owner, entry.id)
    assert repo.restore_library_source(owner, entry.id)
    assert repo.get_library_entry(owner, entry.id) is not None
    repo.trash_library_source(owner, entry.id)
    repo.replace_chunks(entry.id, [Chunk(idx=0, text="hello", page=None)], [[1.0, 0.0, 0.0]])
    assert repo.purge_library_source(owner, entry.id) == (True, entry.storage_path)
    assert repo.get_library_source(entry.id) is None


def test_purge_expired_takes_only_entries_past_their_owners_retention(repo):
    now, later = _user(repo, '{"trash_days": 0}'), _user(repo)
    expired, kept, active = _library(repo, now), _library(repo, later), _library(repo, now)
    repo.trash_library_source(now, expired.id)
    repo.trash_library_source(later, kept.id)
    keys = repo.purge_expired()
    assert expired.storage_path in keys
    assert kept.storage_path not in keys and active.storage_path not in keys
    assert repo.get_library_source(expired.id) is None
    assert repo.get_library_source(kept.id) is not None


def test_the_queue_skips_generated_trashed_and_backed_off_rows(repo):
    _claim_all(repo)
    owner = _user(repo)
    notebook = repo.create_notebook(owner, "nb")
    waiting = _library(repo, owner)
    trashed = _library(repo, owner)
    repo.trash_library_source(owner, trashed.id)
    output = _generated(repo, notebook.id, owner)
    assert _claim_all(repo) == {waiting.id}

    repo.release_for_retry(waiting.id, "boom", 60)
    assert _claim_all(repo) == set()
    source = repo.get_library_source(waiting.id)
    assert source is not None and source.status == "processing" and source.error == "boom"
    assert source.attempts == 1
    repo.release_for_retry(waiting.id, "boom", 0)
    assert _claim_all(repo) == {waiting.id}
    assert output not in _claim_all(repo)


def test_a_stale_claim_is_taken_over_and_counts_an_attempt(repo):
    _claim_all(repo)
    entry = _library(repo, _user(repo))
    assert _claim_all(repo) == {entry.id}
    assert _claim_all(repo) == set()  # held, not stale
    time.sleep(1.1)
    # Every row older than a second is stale now, earlier tests' included.
    assert entry.id in _claim_all(repo, stale=1)
    source = repo.get_library_source(entry.id)
    assert source is not None and source.attempts == 2


def test_concurrent_workers_never_claim_the_same_row(repo):
    _claim_all(repo)
    owner = _user(repo)
    expected = {_library(repo, owner).id for _ in range(20)}
    results: list[set[UUID]] = [set() for _ in range(4)]

    def work(mine: set[UUID]) -> None:
        while (library_id := repo.claim_library_source("w", STALE)) is not None:
            assert library_id not in mine
            mine.add(library_id)

    threads = [threading.Thread(target=work, args=(r,)) for r in results]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert set().union(*results) == expected
    assert sum(len(r) for r in results) == len(expected)


def test_retry_after_failure_resets_the_row(repo):
    _claim_all(repo)
    entry = _library(repo, _user(repo))
    _claim_all(repo)
    repo.release_for_retry(entry.id, "boom", 3600)
    repo.set_library_status(entry.id, "failed", "boom")
    repo.retry_library_source(entry.id)
    source = repo.get_library_source(entry.id)
    assert source is not None and source.status == "processing" and source.error is None
    assert source.attempts == 0
    assert _claim_all(repo) == {entry.id}


def test_claim_seed_only_once_and_only_for_an_empty_library(repo):
    fresh, busy = _user(repo), _user(repo)
    assert repo.claim_seed(fresh)
    assert not repo.claim_seed(fresh)
    _library(repo, busy)
    assert not repo.claim_seed(busy)


def test_credit_and_usage(repo):
    rich, broke = _user(repo), _user(repo, cents=0)
    assert repo.has_credit(rich) and not repo.has_credit(broke)
    assert not repo.is_admin(rich)
    record = repo.record_usage(rich, None, "llm", "llm", 1000, 1000)
    assert record.cost_cents > 0


def test_admin_counts(repo):
    before = repo.admin_stats(STALE)
    [today_before] = repo.admin_daily(1)
    owner = _user(repo)
    notebook = repo.create_notebook(owner, "nb")
    ready, failed = _library(repo, owner, kind="pdf"), _library(repo, owner, kind="image")
    repo.set_library_status(ready.id, "ready")
    repo.set_library_status(failed.id, "failed", "x")
    _generated(repo, notebook.id, owner)
    after = repo.admin_stats(STALE)
    assert after.sources["ready"] == before.sources["ready"] + 1
    assert after.sources["failed"] == before.sources["failed"] + 1
    assert after.source_bytes == before.source_bytes + 20
    days = repo.admin_daily(7)
    assert len(days) == 7 and days[0].day < days[-1].day
    today = days[-1]
    assert today.sources_created == today_before.sources_created + 2
    assert today.by_kind["pdf"] == today_before.by_kind["pdf"] + 1
    assert today.failed == today_before.failed + 1
