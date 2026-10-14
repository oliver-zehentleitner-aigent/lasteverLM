"""A fetched web page is kept as an inert snapshot of what was read."""

from uuid import UUID

from lasteverlm_ingest.loaders.snapshot import html_snapshot, text_snapshot
from lasteverlm_ingest.loaders.url import Fetched
from lasteverlm_ingest.worker import SNAPSHOT_NAME, process_source
from tests.fakes import InMemoryRepository, InMemoryStorage
from tests.test_web_versions import PAGE, Site, _deps, _read_page

HOSTILE = """<html><head><title>Big  news</title><script>alert(1)</script>
<link rel=stylesheet href="https://evil.test/a.css"><style>body{background:url(https://evil.test/x)}</style>
<meta http-equiv="refresh" content="0;url=https://evil.test/"><base href="https://evil.test/"></head>
<body onload="steal()"><h1 style="background:url(https://evil.test/y)">Big news</h1>
<p class="lead" onclick="x()">Read <a href="/more">more</a>, <a href="javascript:alert(2)">this</a>,
<a href="mailto:x@y.z">mail</a>.</p><img src="https://evil.test/t.png" alt="a chart">
<iframe src="https://evil.test/f"></iframe><form action="https://evil.test/"><input name=q></form>
<svg><script>alert(3)</script></svg><object data="https://evil.test/o"></object>
<table><tr><td colspan="2" onmouseover="z()">cell &amp; &lt;b&gt;</td></tr></table></body></html>"""


def test_the_snapshot_keeps_text_and_structure_and_nothing_that_loads_or_runs():
    page = html_snapshot(HOSTILE, "https://news.test/today", "2026-10-14 12:00 UTC")
    body = page.split("<body>", 1)[1]
    for gone in ("script", "alert", "evil.test", "onload", "onclick", "onmouseover", "style=",
                 "iframe", "<form", "<input", "<object", "<svg", "<img", "<link", "<base",
                 "refresh", "javascript:", "mailto:"):  # fmt: skip
        assert gone not in body, gone
    assert "<h1>Big news</h1>" in body
    assert '<a href="https://news.test/more" rel="noreferrer noopener">more</a>' in body
    assert "[a chart]" in body and '<td colspan="2">cell &amp; &lt;b&gt;</td>' in body
    assert "<title>Big news</title>" in page and "Snapshot of https://news.test/today" in page
    assert "default-src 'none'" in page


def test_a_text_page_is_escaped_into_pre():
    page = text_snapshot("a <b> & c", "https://x.test/a.txt", "now")
    assert "<pre>a &lt;b&gt; &amp; c</pre>" in page


class RedirectingSite(Site):
    def fetch(self, url: str) -> Fetched:
        self.fetches += 1
        return Fetched("https://example.org/news/final", "text/html", "utf-8", self.text.encode())


def test_a_read_stores_the_snapshot_and_the_final_address():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    site = RedirectingSite("<html><body><p>Big news today.</p><script>x()</script></body></html>")
    nb, link, lib = _read_page(repo, storage, site)
    page = repo.library[lib]
    assert page.snapshot_path == f"{page.owner}/{lib}/{SNAPSHOT_NAME}"
    assert page.final_url == "https://example.org/news/final" and page.checked_at
    html = storage.objects[page.snapshot_path].decode()
    assert storage.types[page.snapshot_path] == "text/html; charset=utf-8"
    assert "Big news today." in html and "x()" not in html
    # A changed page: its new version gets a snapshot of its own; the old keeps its.
    repo.request_refetch(lib)
    site.text = "<html><body><p>Other news.</p></body></html>"
    process_source(lib, _deps(repo, storage, site))
    new_id = repo.library[lib].superseded_by
    process_source(new_id, _deps(repo, storage, site))
    new = repo.library[new_id]
    assert new.snapshot_path != page.snapshot_path
    assert "Other news." in storage.objects[new.snapshot_path].decode()
    assert "Big news today." in storage.objects[page.snapshot_path].decode()


def test_snapshot_url_on_sources_and_library_and_purged_with_the_page(client, repo, storage):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": PAGE}).json()
    lib = UUID(r["library_id"])
    assert r["snapshot_url"] is None  # not fetched yet
    key = f"{repo.library[lib].owner}/{lib}/{SNAPSHOT_NAME}"
    storage.put(key, b"<html></html>", "text/html; charset=utf-8")
    repo.set_fetched(lib, "h", PAGE, key)
    repo.set_library_status(lib, "ready")
    signed = f"https://storage.test/{key}?expires=3600"
    [source] = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert source["snapshot_url"] == signed and source["final_url"] == PAGE
    [entry] = client.get("/api/ingest/library").json()
    assert entry["snapshot_url"] == signed
    client.delete(f"/api/ingest/library/{lib}")
    assert client.delete(f"/api/ingest/library/{lib}/purge").status_code == 204
    assert key not in storage.objects
