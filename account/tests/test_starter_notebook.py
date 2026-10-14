"""The starter notebook: an admin's notebook with only ready sources, stored for C and D."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import FakeMailer, bearer, login

URL = "/api/account/admin/settings/starter-notebook"


def test_set_read_and_clear(client: TestClient, mailer: FakeMailer, repo: MemoryRepository) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    assert client.get(URL, headers=bearer(token)).json() == {
        "notebook_id": None,
        "owner_id": None,
        "set_at": None,
        "set_by": None,
    }
    nb = uuid.uuid4()
    repo.notebooks[nb] = uuid.UUID(admin["id"])
    repo.sources += [(nb, "ready"), (nb, "ready")]
    r = client.put(URL, json={"notebook_id": str(nb)}, headers=bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert body["notebook_id"] == str(nb) and body["owner_id"] == admin["id"]
    assert body["set_by"] == "admin@example.org" and body["set_at"]
    # stored where ingest and rag read it
    assert repo.settings["starter_notebook"]["notebook_id"] == str(nb)
    assert client.delete(URL, headers=bearer(token)).status_code == 204
    assert client.get(URL, headers=bearer(token)).json()["notebook_id"] is None


def test_refusals(client: TestClient, mailer: FakeMailer, repo: MemoryRepository) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    _, user = login(client, mailer, "user@example.org")
    r = client.put(URL, json={"notebook_id": str(uuid.uuid4())}, headers=bearer(token))
    assert r.status_code == 404 and r.json()["code"] == "unknown_notebook"
    users_nb = uuid.uuid4()
    repo.notebooks[users_nb] = uuid.UUID(user["id"])
    repo.sources.append((users_nb, "ready"))
    r = client.put(URL, json={"notebook_id": str(users_nb)}, headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "owner_not_admin"
    half = uuid.uuid4()
    repo.notebooks[half] = uuid.UUID(admin["id"])
    repo.sources += [(half, "ready"), (half, "processing"), (half, "failed")]
    r = client.put(URL, json={"notebook_id": str(half)}, headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "sources_not_ready"
    assert r.json()["error"].startswith("1 of 3 sources are ready")
    unread = uuid.uuid4()
    repo.notebooks[unread] = uuid.UUID(admin["id"])
    repo.sources += [(unread, "ready")] + [(unread, "added")] * 3
    r = client.put(URL, json={"notebook_id": str(unread)}, headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "sources_not_ready"
    assert r.json()["error"] == (
        "3 sources are not read yet; ask a question or create an output in the notebook"
        " to read them"
    )
    empty = uuid.uuid4()
    repo.notebooks[empty] = uuid.UUID(admin["id"])
    r = client.put(URL, json={"notebook_id": str(empty)}, headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "sources_not_ready"
    assert "starter_notebook" not in repo.settings


def test_viewer_reads_admin_writes(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    _, viewer = login(client, mailer, "v@example.org")
    client.patch(
        f"/api/account/admin/users/{viewer['id']}", json={"role": "viewer"}, headers=bearer(token)
    )
    vtoken, _ = login(client, mailer, "v@example.org")
    assert client.get(URL, headers=bearer(vtoken)).status_code == 200
    assert (
        client.put(URL, json={"notebook_id": str(uuid.uuid4())}, headers=bearer(vtoken)).status_code
        == 403
    )
    assert client.delete(URL, headers=bearer(vtoken)).status_code == 403
