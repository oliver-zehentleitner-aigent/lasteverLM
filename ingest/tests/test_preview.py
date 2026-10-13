from lasteverlm_core import DEMO_USER_ID

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PAGE = "https://example.org/page"


def _notebook(client) -> str:
    return client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]


def _upload(client, nb, name, data, media_type):
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", files={"file": (name, data, media_type)})
    assert r.status_code == 202
    return r.json()


def _signed(source, name) -> str:
    return f"https://storage.test/{DEMO_USER_ID}/{source['library_id']}/{name}?expires=3600"


def test_every_kind_carries_where_the_document_opens_everywhere_it_is_listed(client, storage):
    nb = _notebook(client)
    image = _upload(client, nb, "map.png", PNG, "image/png")
    text = _upload(client, nb, "notes.txt", b"plain notes " * 10, "text/plain")
    pdf = _upload(client, nb, "paper.pdf", b"%PDF-1.4 stub", "application/pdf")
    url = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": PAGE}).json()
    expected = {
        image["id"]: _signed(image, "map.png"),
        text["id"]: _signed(text, "notes.txt"),
        pdf["id"]: _signed(pdf, "paper.pdf"),
        url["id"]: PAGE,
    }
    # The browser renders each object by its stored type.
    assert storage.types[f"{DEMO_USER_ID}/{pdf['library_id']}/paper.pdf"] == "application/pdf"
    assert (
        storage.types[f"{DEMO_USER_ID}/{text['library_id']}/notes.txt"]
        == "text/plain; charset=utf-8"
    )

    for created in (image, text, pdf, url):
        assert created["preview_url"] == expected[created["id"]]
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert {s["id"]: s["preview_url"] for s in listed} == expected

    by_library = {s["library_id"]: expected[s["id"]] for s in (image, text, pdf, url)}
    library = client.get("/api/ingest/library").json()
    assert {e["id"]: e["preview_url"] for e in library} == by_library
    entry = client.get(f"/api/ingest/library/{pdf['library_id']}").json()
    assert entry["preview_url"] == by_library[pdf["library_id"]]
    # The object key stays internal.
    assert "storage_path" not in entry

    for created in (image, url):
        assert client.delete(f"/api/ingest/library/{created['library_id']}").status_code == 204
    trash = client.get("/api/ingest/library/trash").json()
    assert {e["id"]: e["preview_url"] for e in trash} == {
        image["library_id"]: by_library[image["library_id"]],
        url["library_id"]: PAGE,
    }
    assert all("storage_path" not in e for e in trash)


def test_a_generated_row_has_no_preview():
    from lasteverlm_ingest.api.deps import preview_url
    from tests.fakes import InMemoryStorage

    assert preview_url(InMemoryStorage(), "generated", None) is None
    assert preview_url(InMemoryStorage(), "generated", "nb/out/report.md") is None
