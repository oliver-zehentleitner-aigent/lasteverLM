"""The viewer's "Original" view of a text source: its stored text."""

from uuid import uuid4

from lasteverlm_ingest.api import sources


def _upload(client, name, data, media_type="text/plain"):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    return client.post(url, files={"file": (name, data, media_type)}).json()


def test_a_text_source_comes_back_as_text_before_it_is_read(client):
    source = _upload(client, "notes.md", "# Überblick\r\nZeile zwei\n".encode())
    assert source["status"] == "added"
    r = client.get(f"/api/ingest/sources/{source['id']}/text")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.text == "# Überblick\nZeile zwei\n"


def test_latin1_is_decoded_like_the_loader_does(client):
    source = _upload(client, "old.txt", "Grüße".encode("latin-1"))
    assert client.get(f"/api/ingest/sources/{source['id']}/text").text == "Grüße"


def test_other_kinds_are_415_large_texts_413_strangers_404(client, repo, monkeypatch):
    pdf = _upload(client, "a.pdf", b"%PDF-1.4", "application/pdf")
    r = client.get(f"/api/ingest/sources/{pdf['id']}/text")
    assert r.status_code == 415
    monkeypatch.setattr(sources, "MAX_TEXT_BYTES", 10)
    big = _upload(client, "big.txt", b"x" * 11)
    r = client.get(f"/api/ingest/sources/{big['id']}/text")
    assert r.status_code == 413 and "larger than" in r.json()["error"]
    theirs = repo.add_source(repo.create_notebook(uuid4(), "x").id, "t.txt", "text", "k")
    assert client.get(f"/api/ingest/sources/{theirs.id}/text").status_code == 404
