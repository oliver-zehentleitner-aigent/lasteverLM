from lasteverlm_core import DEMO_USER_ID

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _notebook(client) -> str:
    return client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]


def _upload(client, nb, name, data, media_type):
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", files={"file": (name, data, media_type)})
    assert r.status_code == 202
    return r.json()


def test_an_image_carries_a_presigned_preview_everywhere_it_is_listed(client):
    nb = _notebook(client)
    image = _upload(client, nb, "map.png", PNG, "image/png")
    text = _upload(client, nb, "notes.txt", b"plain notes " * 10, "text/plain")
    key = f"{DEMO_USER_ID}/{image['library_id']}/map.png"
    signed = f"https://storage.test/{key}?expires=3600"

    assert image["preview_url"] == signed and text["preview_url"] is None
    listed = {s["id"]: s for s in client.get(f"/api/ingest/notebooks/{nb}/sources").json()}
    assert listed[image["id"]]["preview_url"] == signed
    assert listed[text["id"]]["preview_url"] is None

    library = {e["id"]: e for e in client.get("/api/ingest/library").json()}
    assert library[image["library_id"]]["preview_url"] == signed
    assert library[text["library_id"]]["preview_url"] is None
    entry = client.get(f"/api/ingest/library/{image['library_id']}").json()
    assert entry["preview_url"] == signed
    # The object key stays internal.
    assert "storage_path" not in entry

    assert client.delete(f"/api/ingest/library/{image['library_id']}").status_code == 204
    [trashed] = client.get("/api/ingest/library/trash").json()
    assert trashed["preview_url"] == signed and "storage_path" not in trashed


def test_a_url_source_has_no_preview(client):
    nb = _notebook(client)
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": "https://example.org/page"})
    assert r.status_code == 202 and r.json()["preview_url"] is None
