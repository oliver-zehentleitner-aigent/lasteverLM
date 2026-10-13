"""The live failure of v0.7.1: a worker claimed a library source before its
object was in the bucket (NoSuchKey), and the retry waited ten minutes."""

from datetime import UTC, datetime

from lasteverlm_core import StorageError

from lasteverlm_ingest.worker import process_source
from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage
from tests.test_worker import add_source, deps


def _notebook(client) -> str:
    return client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]


def test_the_object_is_in_the_bucket_before_the_row_exists(client, repo, storage):
    rows_at_put: list[int] = []
    put = storage.put

    def watching_put(key, data, content_type):
        rows_at_put.append(len(repo.library))
        put(key, data, content_type)

    storage.put = watching_put
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    )
    assert r.status_code == 202
    assert rows_at_put == [0] and len(repo.library) == 1


def test_a_failed_put_leaves_no_claimable_row(client, repo, storage):
    def broken_put(key, data, content_type):
        raise StorageError("bucket unreachable")

    storage.put = broken_put
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    )
    assert r.status_code == 503 and "storage unavailable" in r.json()["error"]
    assert repo.library == {} and repo.claim_library_source("w", 600) is None


def test_a_concurrent_duplicate_keeps_one_row_and_drops_the_spare_object(client, repo, storage):
    nb = _notebook(client)
    first = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"same", "text/plain")}
    ).json()
    # The second request does not see the first row when it looks, as if both
    # arrived at once; the insert then finds it.
    find = repo.find_library_source
    repo.find_library_source = lambda owner, key: None
    second = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"same", "text/plain")}
    )
    repo.find_library_source = find
    assert second.json()["library_id"] == first["library_id"]
    assert len(repo.library) == 1 and len(storage.objects) == 1


class MissingOnce(InMemoryStorage):
    """GetObject answers NoSuchKey the first time, like a bucket read that
    came before the object was written."""

    def __init__(self) -> None:
        super().__init__()
        self.misses = 1

    def get(self, key: str) -> bytes:
        if self.misses:
            self.misses -= 1
            raise StorageError("download failed: NoSuchKey on GetObject")
        return super().get(key)


def test_a_missing_object_is_retried_within_seconds():
    repo, storage = InMemoryRepository(), MissingOnce()
    sid = add_source(repo, storage, b"some text that will be there")
    d = deps(repo, storage, FakeEmbedder(8))
    assert repo.claim_library_source("w", 600) == sid
    process_source(sid, d)
    source = repo.library[sid]
    assert source.status == "processing" and "NoSuchKey" in source.error
    wait = (repo.retry_at[sid] - datetime.now(UTC)).total_seconds()
    assert 4 < wait <= 5  # the next attempt in five seconds, not ten minutes
    repo.retry_at[sid] = datetime.now(UTC)
    assert repo.claim_library_source("w2", 600) == sid
    process_source(sid, d)
    assert repo.library[sid].status == "ready" and repo.library[sid].attempts == 2
