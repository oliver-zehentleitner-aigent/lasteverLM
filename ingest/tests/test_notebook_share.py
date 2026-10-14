"""Renaming a notebook and sharing it read-only by a link."""

from uuid import uuid4


def _notebook(client, title="Thesis") -> str:
    return client.post("/api/ingest/notebooks", json={"title": title}).json()["id"]


def test_rename_trims_and_checks_the_title(client, repo):
    nb = _notebook(client)
    url = f"/api/ingest/notebooks/{nb}"
    r = client.patch(url, json={"title": "  Defence  "})
    assert r.status_code == 200 and r.json()["title"] == "Defence" and r.json()["id"] == nb
    assert [n["title"] for n in client.get("/api/ingest/notebooks").json()] == ["Defence"]
    for bad in ("   ", "x" * 201):
        r = client.patch(url, json={"title": bad})
        assert r.status_code == 400 and r.json()["error"] == "title must be 1 to 200 characters"
    # The creation limit: a title made at 200 stays renameable.
    long = _notebook(client, "y" * 200)
    r = client.patch(f"/api/ingest/notebooks/{long}", json={"title": "z" * 200})
    assert r.status_code == 200 and r.json()["title"] == "z" * 200
    assert client.patch(url, json={}).status_code == 422
    theirs = repo.create_notebook(uuid4(), "theirs")
    assert (
        client.patch(f"/api/ingest/notebooks/{theirs.id}", json={"title": "x"}).status_code == 404
    )
    assert repo.notebooks[theirs.id][1].title == "theirs"


def test_share_gives_one_token_until_revoked(client, repo):
    nb = _notebook(client)
    url = f"/api/ingest/notebooks/{nb}/share"
    first = client.post(url)
    assert first.status_code == 200
    token = first.json()["share_token"]
    assert len(token) >= 32
    assert client.post(url).json() == {"share_token": token}  # the same link again
    [listed] = client.get("/api/ingest/notebooks").json()
    assert listed["share_token"] == token
    assert client.delete(url).status_code == 204
    assert client.get("/api/ingest/notebooks").json()[0]["share_token"] is None
    assert client.post(url).json()["share_token"] != token  # a new link


def test_only_the_owner_shares(client, repo):
    theirs = repo.create_notebook(uuid4(), "theirs")
    url = f"/api/ingest/notebooks/{theirs.id}/share"
    assert client.post(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert repo.notebooks[theirs.id][1].share_token is None
