"""Web pages fetched again: unchanged costs nothing, changed is a new version."""

from uuid import UUID

from lasteverlm_ingest.loaders import default_registry
from lasteverlm_ingest.loaders.pdf import PdfLoader
from lasteverlm_ingest.loaders.text import TextLoader
from lasteverlm_ingest.loaders.url import Fetched, UrlLoader
from lasteverlm_ingest.worker import process_source
from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage
from tests.test_worker import USER, deps

PAGE = "https://example.org/news"


class Site:
    """The web page, whatever it says right now."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.fetches = 0

    def fetch(self, url: str) -> Fetched:
        self.fetches += 1
        return Fetched(url, "text/plain", "utf-8", self.text.encode())


def _deps(repo, storage, site):
    d = deps(repo, storage, FakeEmbedder(8))
    loaders = default_registry()
    loaders.register("url", UrlLoader(fetch=site.fetch, text=TextLoader(), pdf=PdfLoader()))
    return d.__class__(**{**d.__dict__, "loaders": loaders})


def _read_page(repo, storage, site):
    nb = repo.create_notebook(USER, "nb")
    link = repo.add_source(nb.id, PAGE, "url", "page-key", dedupe_key=f"url:{PAGE}")
    storage.put("page-key", PAGE.encode(), "text/uri-list")
    lib = link.library_id
    repo.queue_for_processing(USER, [lib]) if repo.library[lib].status == "added" else None
    process_source(lib, _deps(repo, storage, site))
    assert repo.library[lib].status == "ready" and repo.library[lib].fetched_at
    return nb, link, lib


def test_an_unchanged_page_costs_nothing_and_keeps_its_version():
    repo, storage, site = InMemoryRepository(), InMemoryStorage(), Site("Big news today.")
    nb, link, lib = _read_page(repo, storage, site)
    first, usage = repo.library[lib], len(repo.usage)
    assert repo.request_refetch(lib).status == "processing"
    # The same text with other spacing: no new version.
    process_source(lib, _deps(repo, storage, Site("Big  news\n today.")))
    page = repo.library[lib]
    assert page.status == "ready" and page.version == 1
    # The version's fetch time and snapshot stay; only the check is newer.
    assert page.fetched_at == first.fetched_at and page.snapshot_path == first.snapshot_path
    assert page.checked_at >= first.checked_at
    assert page.superseded_by is None and page.refetch_requested_at is None
    assert len(repo.usage) == usage  # nothing read, nothing charged
    assert [s.library_id for s in repo.list_sources(nb.id)] == [lib]


def test_a_changed_page_becomes_a_new_version_that_takes_the_links():
    repo, storage, site = InMemoryRepository(), InMemoryStorage(), Site("Big news today.")
    nb, link, lib = _read_page(repo, storage, site)
    old_chunks = list(repo.chunks[lib])
    repo.request_refetch(lib)
    site.text = "Even bigger news tomorrow."
    process_source(lib, _deps(repo, storage, site))
    old = repo.library[lib]
    assert old.superseded_by is not None and old.status == "ready" and old.dedupe_key is None
    new = repo.library[old.superseded_by]
    assert new.version == 2 and new.status == "processing" and new.dedupe_key == f"url:{PAGE}"
    # The notebook links the new version; the old keeps its chunks for citations.
    assert [s.library_id for s in repo.list_sources(nb.id)] == [new.id]
    assert repo.chunks[lib] == old_chunks
    process_source(new.id, _deps(repo, storage, site))
    assert repo.library[new.id].status == "ready"
    assert {u.action_id for u in repo.usage} == {lib, new.id}  # the new version is charged


def test_refetch_endpoint_and_lists(client, repo, storage):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": PAGE})
    source, lib = r.json()["id"], UUID(r.json()["library_id"])
    assert r.json()["version"] == 1 and r.json()["fetched_at"] is None
    url = f"/api/ingest/sources/{source}/refetch"
    # Unread: refetch simply reads it.
    first = client.post(url)
    assert first.status_code == 202 and first.json()["version"] == 1
    assert repo.library[lib].status == "processing"
    assert client.post(url).status_code == 409  # being read
    repo.set_library_status(lib, "ready")
    assert client.post(url).status_code == 202
    assert repo.library[lib].refetch_requested_at is not None
    # A new version is listed, the old one is not; the old stays reachable by id.
    repo.set_library_status(lib, "ready")
    new = repo.new_version(lib)
    listed = client.get("/api/ingest/library").json()
    assert [(e["id"], e["version"]) for e in listed] == [(str(new), 2)]
    assert repo.get_library_source(lib) is not None
    txt = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"x", "text/plain")}
    ).json()["id"]
    assert client.post(f"/api/ingest/sources/{txt}/refetch").status_code == 409  # no web page


def test_purging_a_page_purges_its_older_versions(client, repo, storage):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    lib = UUID(
        client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": PAGE}).json()["library_id"]
    )
    repo.set_library_status(lib, "ready")
    new = repo.new_version(lib)
    client.delete(f"/api/ingest/library/{new}")
    assert client.delete(f"/api/ingest/library/{new}/purge").status_code == 204
    assert lib not in repo.library and new not in repo.library
