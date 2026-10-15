"""A user who deleted their starter notebook can have it made again from
the help page: free, at most one an hour, asking first when they still
have one."""

from uuid import UUID

from lasteverlm_ingest.repository import StarterRef
from tests.test_starter import _starter

URL = "/api/ingest/starter/copy"


def _seeded(client, repo, storage):
    """The starter set, the user seeded by their first notebook list."""
    _, made = _starter(repo, storage)
    [first] = client.get("/api/ingest/notebooks").json()
    assert first["starter"] is True
    return first, made


def test_after_deleting_the_starter_notebook_it_comes_back_with_the_same_sources(
    client, repo, storage
):
    first, made = _seeded(client, repo, storage)
    library = {e["id"] for e in client.get("/api/ingest/library").json()}
    assert client.delete(f"/api/ingest/notebooks/{first['id']}").status_code == 204
    handovers = len(repo.output_copies)
    r = client.post(URL)
    assert r.status_code == 201, r.text
    again = r.json()
    assert again["starter"] is True and again["title"] == first["title"]
    assert again["id"] != first["id"]
    listed = client.get(f"/api/ingest/notebooks/{again['id']}/sources").json()
    assert sorted(s["name"] for s in listed) == sorted(made)
    assert all(s["status"] == "ready" and s["starter"] for s in listed)
    # The sources the user still had are linked, not copied a second time.
    assert {s["library_id"] for s in listed} == library
    assert {e["id"] for e in client.get("/api/ingest/library").json()} == library
    # Rag gets its handover for the outputs, as at the first sign-in.
    assert len(repo.output_copies) == handovers + 1
    target, _, owner, maps = repo.output_copies[-1]
    assert str(target) == again["id"] and set(maps["source_map"].values()) >= library
    assert maps["chunk_map"]  # the starter's chunks map onto the user's own


def test_a_trashed_source_is_restored_and_a_purged_one_copied_fresh(client, repo, storage):
    first, made = _seeded(client, repo, storage)
    entries = {e["name"]: e["id"] for e in client.get("/api/ingest/library").json()}
    client.delete(f"/api/ingest/notebooks/{first['id']}")
    trashed, purged = entries["faq.txt"], entries["handbook.pdf"]
    assert client.delete(f"/api/ingest/library/{trashed}").status_code == 204
    assert client.delete(f"/api/ingest/library/{purged}").status_code == 204
    assert client.delete(f"/api/ingest/library/{purged}/purge").status_code == 204
    again = client.post(URL).json()
    listed = {
        s["name"]: s["library_id"]
        for s in client.get(f"/api/ingest/notebooks/{again['id']}/sources").json()
    }
    assert listed["faq.txt"] == trashed and repo.library[UUID(trashed)].deleted_at is None
    assert listed["handbook.pdf"] != purged and UUID(listed["handbook.pdf"]) in repo.library
    assert repo.library[UUID(listed["handbook.pdf"])].status == "ready"
    assert sorted(listed) == sorted(made)


def test_with_a_starter_notebook_it_asks_first_and_force_makes_another(client, repo, storage):
    _seeded(client, repo, storage)
    r = client.post(URL)
    assert r.status_code == 409 and r.json() == {"error": "starter_exists"}
    assert len(client.get("/api/ingest/notebooks").json()) == 1
    r = client.post(f"{URL}?force=true")
    assert r.status_code == 201
    assert [n["starter"] for n in client.get("/api/ingest/notebooks").json()] == [True, True]


def test_at_most_one_copy_an_hour(client, repo, storage):
    first, _ = _seeded(client, repo, storage)
    client.delete(f"/api/ingest/notebooks/{first['id']}")
    assert client.post(URL).status_code == 201  # the first sign-in's copy does not count
    r = client.post(f"{URL}?force=true")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "starter_copy_too_soon" and 3500 < body["retry_after"] <= 3600
    assert r.headers["Retry-After"] == str(body["retry_after"])
    assert len(client.get("/api/ingest/notebooks").json()) == 1


def test_without_a_starter_it_is_404_no_starter(client, repo):
    r = client.post(URL)
    assert r.status_code == 404 and r.json() == {"error": "no_starter"}
    # A starter whose notebook is gone counts as none.
    from uuid import uuid4

    repo.starter = StarterRef(owner_id=uuid4(), notebook_id=uuid4())
    r = client.post(URL)
    assert r.status_code == 404 and r.json() == {"error": "no_starter"}


def test_a_user_never_seeded_gets_a_full_copy(client, repo, storage):
    """Seeded before the starter existed, or never listed: the copy works
    the same, every source copied."""
    _, made = _starter(repo, storage)
    r = client.post(URL)
    assert r.status_code == 201
    listed = client.get(f"/api/ingest/notebooks/{r.json()['id']}/sources").json()
    assert sorted(s["name"] for s in listed) == sorted(made)
