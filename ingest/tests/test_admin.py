from uuid import uuid4

from lasteverlm_core import DEMO_USER_ID

from tests.test_loaders import minimal_pdf


def test_admin_stats_needs_a_token_and_an_admin(client, repo):
    r = client.get("/api/ingest/admin/stats", headers={"Authorization": ""})
    assert r.status_code == 401
    r = client.get("/api/ingest/admin/stats")
    assert r.status_code == 403 and r.json() == {"error": "admin only"}


def test_admin_stats_counts_across_users(client, repo, run_queue):
    repo.admins.add(DEMO_USER_ID)
    empty = client.get("/api/ingest/admin/stats")
    assert empty.status_code == 200
    assert empty.json() == {
        "sources": {"processing": 0, "ready": 0, "failed": 0},
        "jobs": {"pending": 0, "running": 0, "failed": 0},
        "chunks": 0,
        "source_bytes": 0,
    }
    nb = client.post("/api/ingest/notebooks", json={"title": "s"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    pdf = minimal_pdf(["one page of text"])
    client.post(url, files={"file": ("a.pdf", pdf, "application/pdf")})
    client.post(url, files={"file": ("b.txt", b"   ", "text/plain")})
    run_queue()
    client.post(url, files={"file": ("c.txt", b"waiting", "text/plain")})
    other = repo.create_notebook(uuid4(), "someone else's")
    repo.create_source(other.id, uuid4(), "d.txt", "text", "k", 10)
    repo.claim_source("w", 600)

    stats = client.get("/api/ingest/admin/stats").json()
    assert stats["sources"] == {"processing": 2, "ready": 1, "failed": 1}
    assert stats["jobs"] == {"pending": 1, "running": 1, "failed": 1}
    assert stats["chunks"] >= 1
    assert stats["source_bytes"] == len(pdf) + 3 + len(b"waiting") + 10


def test_admins_are_never_out_of_credit(client, repo):
    repo.default_balance = 0
    nb = client.post("/api/ingest/notebooks", json={"title": "x"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    files = {"file": ("a.txt", b"text", "text/plain")}
    assert client.post(url, files=files).status_code == 402
    repo.admins.add(DEMO_USER_ID)
    assert client.post(url, files=files).status_code == 202
