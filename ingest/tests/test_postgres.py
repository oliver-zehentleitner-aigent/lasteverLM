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
from lasteverlm_core import Chunk, PricingRules, Usage, parse_model_prices

from lasteverlm_ingest.repository import STALLED, NewLibrarySource, PostgresRepository, StarterCopy

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("INGEST_TEST_DATABASE_URL")
REPO = Path(__file__).resolve().parents[2]
DIMENSION = 3
PRICES = parse_model_prices('{"llm": {"in": 100, "out": 300}, "emb": {"in": 10, "out": 0}}')
MIGRATION_DIRS = ["infra", "core", "account", "ingest", "rag"]
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
                # Account seeds the pricing rules with a rate in production;
                # without one no usage can be booked.
                conn.execute(
                    "insert into settings (key, value) values ('pricing', %s::jsonb) "
                    "on conflict (key) do nothing",
                    ('{"usd_per_eur": 1}',),
                )
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
    assert repo.purge_library_source(stranger, entry.id) == (False, [])
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


def test_deleting_a_notebook_keeps_its_library_and_its_outputs(repo):
    owner = _user(repo)
    notebook = repo.create_notebook(owner, "nb")
    entry = _library(repo, owner)
    repo.link_source(notebook.id, entry.id)
    output = _generated(repo, notebook.id, owner)
    assert [e.id for e in repo.list_library(owner)] == [entry.id]
    repo.delete_notebook(owner, notebook.id)
    # Only the links went: outputs are rag's, it trashes and purges them.
    assert repo.get_library_source(output) is not None
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
    assert repo.purge_library_source(owner, entry.id) == (False, [])  # not in the trash
    repo.trash_library_source(owner, entry.id)
    assert repo.restore_library_source(owner, entry.id)
    assert repo.get_library_entry(owner, entry.id) is not None
    repo.trash_library_source(owner, entry.id)
    repo.replace_chunks(entry.id, [Chunk(idx=0, text="hello", page=None)], [[1.0, 0.0, 0.0]])
    assert repo.purge_library_source(owner, entry.id) == (True, [entry.storage_path])
    assert repo.get_library_source(entry.id) is None


def test_a_converted_recording_is_read_and_purged_with_its_original(repo):
    owner = _user(repo)
    entry = _library(repo, owner)
    repo.set_transcribed_path(entry.id, f"{owner}/{entry.id}/_transcribed.mp3")
    assert (
        repo.get_library_source(entry.id).transcribed_path == f"{owner}/{entry.id}/_transcribed.mp3"
    )
    notebook = repo.create_notebook(owner, "nb")
    repo.link_source(notebook.id, entry.id)
    [source] = repo.list_sources(notebook.id)
    [listed] = repo.list_library(owner)
    assert (
        source.transcribed_path == listed.transcribed_path == f"{owner}/{entry.id}/_transcribed.mp3"
    )
    repo.trash_library_source(owner, entry.id)
    [trashed] = repo.list_trash(owner)
    assert trashed.transcribed_path == listed.transcribed_path
    assert repo.purge_library_source(owner, entry.id) == (
        True,
        [entry.storage_path, f"{owner}/{entry.id}/_transcribed.mp3"],
    )


def test_deleting_a_users_data_leaves_other_users_alone(repo):
    gone, kept = _user(repo), _user(repo)
    doc = _library(repo, gone)
    rec = _library(repo, gone, kind="audio", name="talk.m4a")
    repo.set_transcribed_path(rec.id, f"{gone}/{rec.id}/_transcribed.mp3")
    repo.trash_library_source(gone, rec.id)
    notebook = repo.create_notebook(gone, "nb")
    repo.link_source(notebook.id, doc.id)
    repo.replace_chunks(doc.id, [Chunk(idx=0, text="hello", page=None)], [[1.0, 0.0, 0.0]])
    _execute(
        repo,
        "insert into library_sources (id, owner, name, kind, status) "
        "values (%s, %s, 'Report', 'generated', 'ready')",
        (uuid4(), gone),
    )
    _execute(repo, "insert into library_seeds (owner) values (%s)", (gone,))
    other = _library(repo, kept)
    other_notebook = repo.create_notebook(kept, "theirs")

    assert repo.user_object_keys(gone) == [
        doc.storage_path,
        rec.storage_path,
        f"{gone}/{rec.id}/_transcribed.mp3",
    ]
    repo.delete_user_data(gone)
    assert repo.user_object_keys(gone) == []
    assert repo.list_library(gone) == [] and repo.list_trash(gone) == []
    assert repo.get_notebook(gone, notebook.id) is None
    assert not repo.is_seeded(gone)  # the seed mark went too
    assert repo.get_library_source(other.id) is not None
    assert repo.get_notebook(kept, other_notebook.id) is not None
    repo.delete_user_data(gone)  # nothing left: no error


def _output(repo, notebook_id, owner, status="ready"):
    """What rag writes for a finished output: the generated library row,
    its link into the notebook (link id = library id) and the outputs row
    naming both."""
    library_id = uuid4()
    _execute(
        repo,
        "insert into library_sources (id, owner, name, kind, status) "
        "values (%s, %s, 'Report', 'generated', %s)",
        (library_id, owner, status),
    )
    _execute(
        repo,
        "insert into sources (id, notebook_id, library_source_id) values (%s, %s, %s)",
        (library_id, notebook_id, library_id),
    )
    _execute(
        repo,
        "insert into outputs (id, notebook_id, kind, status, source_id, owner, origin_title) "
        "select %s, n.id, 'report', 'ready', %s, n.owner, n.title from notebooks n where n.id = %s",
        (uuid4(), library_id, notebook_id),
    )
    return library_id


def test_outputs_are_listed_with_their_origin_and_outlive_their_notebook(repo):
    owner, stranger = _user(repo), _user(repo)
    origin = repo.create_notebook(owner, "Thesis")
    other = repo.create_notebook(owner, "Talk")
    report = _output(repo, origin.id, owner)
    _output(repo, origin.id, owner, status="processing")
    _output(repo, repo.create_notebook(stranger, "x").id, stranger)
    upload = _library(repo, owner)

    [entry] = repo.list_generated(owner)
    assert entry.id == report and entry.origin is not None
    assert (entry.origin.id, entry.origin.title) == (origin.id, "Thesis")
    assert [n.title for n in entry.notebooks] == ["Thesis"]
    assert [e.id for e in repo.list_library(owner)] == [upload.id]  # uploads only

    assert repo.linkable(owner, report) and repo.linkable(owner, upload.id)
    assert not repo.linkable(stranger, report)
    source, created = repo.link_source(other.id, report)
    assert created and source.kind == "generated" and source.status == "ready"

    # Unlinked from its origin: the origin still names it.
    repo.detach_source(report)  # the origin link's id is the library id
    [entry] = repo.list_generated(owner)
    assert entry.origin.id == origin.id and [n.title for n in entry.notebooks] == ["Talk"]
    # The origin deleted: rag's snapshot names it, the row stays.
    repo.delete_notebook(owner, origin.id)
    [entry] = repo.list_generated(owner)
    assert (entry.origin.id, entry.origin.title) == (None, "Thesis")
    # rag's trash marks the generated row; it is neither listed nor linkable.
    _execute(repo, "update library_sources set deleted_at = now() where id = %s", (report,))
    assert repo.list_generated(owner) == [] and not repo.linkable(owner, report)


def test_link_many_links_in_one_go_and_never_doubles(repo):
    owner, stranger = _user(repo), _user(repo)
    origin = repo.create_notebook(owner, "Thesis")
    target = repo.create_notebook(owner, "Talk")
    a, b = _library(repo, owner), _library(repo, owner)
    report = _output(repo, origin.id, owner)
    repo.link_source(target.id, a.id)

    result = repo.link_many(owner, target.id, [a.id, b.id, report])
    assert (result.added, result.already, result.missing) == ([b.id, report], [a.id], [])
    assert {s.library_id for s in repo.list_sources(target.id)} == {a.id, b.id, report}
    again = repo.link_many(owner, target.id, [report, b.id])
    assert (again.added, again.already) == ([], [report, b.id])
    assert len(repo.list_sources(target.id)) == 3

    theirs = _library(repo, stranger)
    trashed = _library(repo, owner)
    repo.trash_library_source(owner, trashed.id)
    fresh = _library(repo, owner)
    refused = repo.link_many(owner, target.id, [fresh.id, theirs.id, trashed.id])
    assert refused.missing == [theirs.id, trashed.id] and refused.added == []
    assert fresh.id not in {s.library_id for s in repo.list_sources(target.id)}
    [entry] = repo.list_generated(owner)
    assert entry.output_id is not None


def test_rename_and_share_a_notebook(repo):
    owner, stranger = _user(repo), _user(repo)
    notebook = repo.create_notebook(owner, "Thesis")
    assert notebook.share_token is None
    assert repo.rename_notebook(stranger, notebook.id, "x") is None
    assert repo.rename_notebook(owner, notebook.id, "Defence").title == "Defence"
    assert repo.share_notebook(stranger, notebook.id) is None
    token = repo.share_notebook(owner, notebook.id)
    assert token and repo.share_notebook(owner, notebook.id) == token
    assert repo.get_notebook(owner, notebook.id).share_token == token
    assert not repo.unshare_notebook(stranger, notebook.id)
    assert repo.unshare_notebook(owner, notebook.id)
    assert repo.list_notebooks(owner)[0].share_token is None
    assert repo.share_notebook(owner, notebook.id) != token


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


def test_the_queue_waits_for_credit_without_counting_attempts(repo):
    _claim_all(repo)
    broke = _user(repo, cents=0)
    waiting = _library(repo, broke)
    starter = _library(repo, broke, starter=True)  # no sponsor: it waits too
    assert _claim_all(repo) == set()
    assert repo.get_library_source(waiting.id).attempts == 0
    _execute(repo, "update library_sources set status = 'ready' where id = %s", (starter.id,))
    _execute(
        repo,
        "insert into ledger (user_id, amount_cents, reason) values (%s, 100, 'voucher')",
        (broke,),
    )
    assert repo.claim_library_source("w", STALE) == waiting.id
    # Credit runs out mid-job: back in the queue, the attempt not counted.
    repo.release_waiting(waiting.id)
    row = repo.get_library_source(waiting.id)
    assert row.attempts == 0 and row.status == "processing" and row.error is None
    _execute(repo, "delete from ledger where user_id = %s", (broke,))
    assert repo.claim_library_source("w", STALE) is None


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


def test_a_row_that_stalled_every_attempt_is_failed_not_handed_out_again(repo):
    """A source that kills or hangs its worker would otherwise take every
    worker in turn, once per claim timeout, forever."""
    _claim_all(repo)
    entry = _library(repo, _user(repo))
    for attempt in (1, 2, 3):
        time.sleep(1.1)
        assert entry.id in _claim_all(repo, stale=1)
        source = repo.get_library_source(entry.id)
        assert source is not None and source.attempts == attempt
    time.sleep(1.1)
    assert entry.id not in _claim_all(repo, stale=1)
    source = repo.get_library_source(entry.id)
    assert source is not None and (source.status, source.error) == ("failed", STALLED)
    # A third attempt still in time is left alone.
    held = _library(repo, _user(repo))
    _execute(repo, "update library_sources set attempts = 2 where id = %s", (held.id,))
    assert held.id in _claim_all(repo)
    assert held.id not in _claim_all(repo)
    source = repo.get_library_source(held.id)
    assert source is not None and source.status == "processing" and source.attempts == 3


def test_a_refreshed_claim_is_not_stale(repo):
    _claim_all(repo)
    entry, idle = _library(repo, _user(repo)), _library(repo, _user(repo))
    assert _claim_all(repo) == {entry.id, idle.id}
    time.sleep(1.1)
    repo.refresh_claim(entry.id)
    taken = _claim_all(repo, stale=1)
    assert idle.id in taken and entry.id not in taken
    # A row nobody holds is not claimed by a refresh.
    unclaimed = _library(repo, _user(repo))
    repo.refresh_claim(unclaimed.id)
    source = repo.get_library_source(unclaimed.id)
    assert source is not None and source.attempts == 0
    assert unclaimed.id in _claim_all(repo)


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


def test_the_starter_notebook_is_copied_once_with_chunks_and_the_handover(repo):
    admin, user, busy = _user(repo), _user(repo), _user(repo)
    starter = repo.create_notebook(admin, "Getting started")
    doc = _library(repo, admin, kind="pdf", name="handbook.pdf", capture="text")
    repo.set_library_status(doc.id, "ready")
    repo.set_library_summary(doc.id, "the handbook")
    repo.replace_chunks(
        doc.id,
        [Chunk(idx=0, text="one", page=1), Chunk(idx=1, text="two", page=2)],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    link, _ = repo.link_source(starter.id, doc.id)
    waiting = _library(repo, admin)  # still processing: not copied
    repo.link_source(starter.id, waiting.id)
    _output(repo, starter.id, admin)  # rag's: not copied by ingest

    _execute(
        repo,
        "insert into settings (key, value) values ('starter_notebook', %s::jsonb) "
        "on conflict (key) do update set value = excluded.value",
        (f'{{"owner_id": "{admin}", "notebook_id": "{starter.id}", "set_by": "x"}}',),
    )
    ref = repo.starter_ref()
    assert ref is not None and (ref.owner_id, ref.notebook_id) == (admin, starter.id)
    [source] = repo.starter_sources(ref)
    assert (source.link_id, source.library.id) == (link.id, doc.id)

    new_lib, new_link, new_nb = uuid4(), uuid4(), uuid4()
    plan = StarterCopy(
        owner=user,
        source_notebook=starter.id,
        notebook_id=new_nb,
        title="Getting started",
        sources=[(source, new_lib, new_link, f"{user}/{new_lib}/handbook.pdf", None)],
    )
    maps = repo.copy_starter(plan)
    assert maps is not None and repo.is_seeded(user)
    copy = repo.get_library_source(new_lib)
    assert copy.owner == user and copy.starter and copy.status == "ready"
    assert copy.summary == "the handbook" and copy.capture == "text"
    assert [s.id for s in repo.list_sources(new_nb)] == [new_link]
    assert maps["source_map"] == {str(link.id): str(new_link), str(doc.id): str(new_lib)}
    with repo.connection() as conn:
        old_chunks = conn.execute(
            "select id, idx, embedding::text from chunks where library_source_id = %s order by idx",
            (doc.id,),
        ).fetchall()
        new_chunks = conn.execute(
            "select id, idx, embedding::text from chunks where library_source_id = %s order by idx",
            (new_lib,),
        ).fetchall()
        handover = conn.execute(
            "select source_notebook, owner, source_map, chunk_map from output_copies "
            "where target_notebook = %s",
            (new_nb,),
        ).fetchone()
    assert [(i, e) for _, i, e in old_chunks] == [(i, e) for _, i, e in new_chunks]
    pairs = zip(old_chunks, new_chunks, strict=True)
    assert maps["chunk_map"] == {str(o[0]): str(n[0]) for o, n in pairs}
    assert handover == (starter.id, user, maps["source_map"], maps["chunk_map"])
    # Once per user, and never into a library that has entries.
    again = plan.model_copy(update={"notebook_id": uuid4()})
    assert repo.copy_starter(again) is None
    _library(repo, busy)
    assert (
        repo.copy_starter(plan.model_copy(update={"owner": busy, "notebook_id": uuid4()})) is None
    )
    _execute(repo, "delete from settings where key = 'starter_notebook'")
    assert repo.starter_ref() is None


def test_the_exchange_rate_is_read_from_the_pricing_row(database_url, repo):
    assert repo.has_exchange_rate()
    with repo.connection() as conn:
        seeded = conn.execute("select value::text from settings where key = 'pricing'").fetchone()[
            0
        ]
    _execute(repo, "update settings set value = '{}'::jsonb where key = 'pricing'", ())
    try:
        fresh = PostgresRepository(database_url, model_prices=PRICES)  # its own cache
        try:
            assert not fresh.has_exchange_rate()
        finally:
            fresh.close()
    finally:
        _execute(repo, "update settings set value = %s::jsonb where key = 'pricing'", (seeded,))


def test_credit_and_usage(repo):
    rich, broke = _user(repo), _user(repo, cents=0)
    assert repo.has_credit(rich) and not repo.has_credit(broke)
    action_id = uuid4()
    record = repo.record_usage(
        rich, None, "source:text", action_id, Usage("llm", "llm", 1000, 1000)
    )
    assert record.cost_cents > 0 and record.charge_cents >= record.cost_cents
    # Converted at the seeded rate (account's migration, or the fixture's).
    assert record.usd_per_eur is not None
    rules = PricingRules(usd_per_eur=record.usd_per_eur)
    assert record.cost_cents == rules.cost_eur_cents(record.cost_usd_cents)
    assert (record.action, record.action_id) == ("source:text", action_id)


def test_admin_counts(repo):
    before = repo.admin_stats(STALE)
    [today_before] = repo.admin_daily(1)
    owner = _user(repo)
    notebook = repo.create_notebook(owner, "nb")
    ready, failed = _library(repo, owner, kind="pdf"), _library(repo, owner, kind="image")
    repo.set_library_status(ready.id, "ready")
    repo.set_library_status(failed.id, "failed", "x")
    _generated(repo, notebook.id, owner)
    broke = _user(repo, cents=0)
    _library(repo, broke)  # queued, its owner without credit
    after = repo.admin_stats(STALE)
    assert after.jobs["waiting_for_credit"] == before.jobs["waiting_for_credit"] + 1
    assert after.jobs["pending"] == before.jobs["pending"]
    assert after.sources["ready"] == before.sources["ready"] + 1
    assert after.sources["failed"] == before.sources["failed"] + 1
    assert after.source_bytes == before.source_bytes + 30
    days = repo.admin_daily(7)
    assert len(days) == 7 and days[0].day < days[-1].day
    today = days[-1]
    assert today.sources_created == today_before.sources_created + 3
    assert today.by_kind["pdf"] == today_before.by_kind["pdf"] + 1
    assert today.failed == today_before.failed + 1
