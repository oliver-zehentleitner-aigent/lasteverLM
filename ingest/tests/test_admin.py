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
    repo.add_source(other.id, "d.txt", "text", "k", 10)
    repo.add_source(other.id, "report", "generated", None)  # rag's, never counted
    repo.claim_library_source("w", 600)

    stats = client.get("/api/ingest/admin/stats").json()
    assert stats["sources"] == {"processing": 2, "ready": 1, "failed": 1}
    assert stats["jobs"] == {"pending": 1, "running": 1, "failed": 1}
    assert stats["chunks"] >= 1
    assert stats["source_bytes"] == len(pdf) + 3 + len(b"waiting") + 10


def test_admins_need_credit_like_everyone(client, repo):
    """core's rule: a positive balance for every user, admins included."""
    repo.default_balance = 0
    nb = client.post("/api/ingest/notebooks", json={"title": "x"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    files = {"file": ("a.txt", b"text", "text/plain")}
    repo.admins.add(DEMO_USER_ID)
    assert client.post(url, files=files).status_code == 402


def test_daily_stats_every_day_oldest_first(client, repo):
    from datetime import UTC, datetime, timedelta

    r = client.get("/api/ingest/admin/stats/daily")
    assert r.status_code == 403
    repo.admins.add(DEMO_USER_ID)
    nb = repo.create_notebook(uuid4(), "nb")
    today = datetime.now(UTC)
    pdf = repo.add_source(nb.id, "a.pdf", "pdf", "k1")
    url = repo.add_source(nb.id, "https://x.org/", "url", "k2")
    old = repo.add_source(nb.id, "b.txt", "text", "k3")
    repo.add_source(nb.id, "report", "generated", None)  # never counted
    repo.set_library_status(url.library_id, "failed", "404")
    repo.library[old.library_id] = repo.library[old.library_id].model_copy(
        update={"created_at": today - timedelta(days=2)}
    )

    days = client.get("/api/ingest/admin/stats/daily?days=3").json()["days"]
    assert [d["day"] for d in days] == [
        (today - timedelta(days=n)).date().isoformat() for n in (2, 1, 0)
    ]
    assert days[0] == {
        "day": days[0]["day"],
        "sources_created": 1,
        "by_kind": {"pdf": 0, "text": 1, "url": 0, "image": 0},
        "failed": 0,
    }
    assert days[1]["sources_created"] == 0 and days[1]["by_kind"]["pdf"] == 0
    assert days[2]["sources_created"] == 2 and days[2]["failed"] == 1
    assert days[2]["by_kind"] == {"pdf": 1, "text": 0, "url": 1, "image": 0}
    assert pdf.library_id in repo.library
    assert len(client.get("/api/ingest/admin/stats/daily").json()["days"]) == 30
    for bad in (0, 366, "x"):
        assert client.get(f"/api/ingest/admin/stats/daily?days={bad}").status_code == 422
