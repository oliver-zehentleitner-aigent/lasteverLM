"""The admin System page: service probes, the Kubernetes read, and life outside a cluster."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.config import Settings
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import AccountService
from lasteverlm_account.system import ServiceStatus, SystemProbe

from .conftest import FakeMailer, bearer, login

PODS = {
    "items": [
        {
            "metadata": {
                "name": "account-7d9f-abc",
                "labels": {"app.kubernetes.io/name": "account"},
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "ghcr.io/x/lasteverlm-account:0.6.0"}],
            },
            "status": {
                "startTime": "2026-10-13T08:00:00Z",
                "containerStatuses": [{"ready": True, "restartCount": 2}],
            },
        },
        {
            "metadata": {"name": "rag-1", "labels": {"app.kubernetes.io/name": "rag"}},
            "spec": {"containers": [{"image": "registry/lasteverlm-rag@sha256:abc"}]},
            "status": {"containerStatuses": [{"ready": False, "restartCount": 0}]},
        },
    ]
}
DEPLOYMENTS = {
    "items": [
        {
            "metadata": {"name": "account"},
            "spec": {"replicas": 2},
            "status": {"readyReplicas": 2, "updatedReplicas": 2},
        },
        {"metadata": {"name": "rag"}, "spec": {"replicas": 1}, "status": {"readyReplicas": 0}},
    ]
}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "ingest":
        return httpx.Response(200, json={"status": "ok", "version": "0.6.0", "commit": "abc1234"})
    if request.url.host == "rag":
        raise httpx.ConnectError("connection refused")
    if request.url.host == "kube":
        assert request.headers["authorization"] == "Bearer sa-token"
        if request.url.path.endswith("/pods"):
            assert "/namespaces/lasteverlm/" in request.url.path
            return httpx.Response(200, json=PODS)
        if request.url.path.endswith("/deployments"):
            return httpx.Response(200, json=DEPLOYMENTS)
    return httpx.Response(404)


@pytest.fixture
def sa_dir(tmp_path: Path) -> Path:
    (tmp_path / "token").write_text("sa-token\n")
    (tmp_path / "namespace").write_text("lasteverlm")
    (tmp_path / "ca.crt").write_text("not a real certificate")
    return tmp_path


def probe(sa_dir: Path, api_base: str | None = "https://kube:443") -> SystemProbe:
    services = [("ingest", "http://ingest/healthz"), ("rag", "http://rag/healthz")]
    return SystemProbe(
        services,
        api_base=api_base,
        serviceaccount_dir=sa_dir,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.anyio
async def test_snapshot_inside_a_cluster(sa_dir: Path) -> None:
    own = ServiceStatus("account", "0.6.0", "abc1234", True)
    snap = await probe(sa_dir).snapshot(own)
    assert snap.cluster is True
    assert [(s.name, s.healthy, s.version) for s in snap.services] == [
        ("account", True, "0.6.0"),
        ("ingest", True, "0.6.0"),
        ("rag", False, None),  # unreachable: healthy false, the response still comes
    ]
    pods = {p.name: p for p in snap.pods}
    a = pods["account-7d9f-abc"]
    assert (a.service, a.image_tag, a.ready, a.restarts, a.node) == (
        "account",
        "0.6.0",
        True,
        2,
        "node-1",
    )
    assert a.started_at is not None and a.started_at.isoformat().startswith("2026-10-13T08:00:00")
    r = pods["rag-1"]
    assert (r.image_tag, r.ready, r.node, r.started_at) == (None, False, None, None)
    assert [(d.name, d.replicas, d.ready, d.updated) for d in snap.deployments] == [
        ("account", 2, 2, 2),
        ("rag", 1, 0, 0),
    ]


@pytest.mark.anyio
async def test_outside_a_cluster_lists_are_empty(tmp_path: Path) -> None:
    snap = await probe(tmp_path, api_base=None).snapshot(ServiceStatus("account", "dev", "x", True))
    assert snap.cluster is False and snap.pods == [] and snap.deployments == []
    assert [s.name for s in snap.services] == ["account", "ingest", "rag"]
    # an API host without a token file is "not a cluster" too
    assert (
        await probe(tmp_path).snapshot(ServiceStatus("account", "dev", "x", True))
    ).cluster is False


@pytest.mark.anyio
async def test_unreadable_kubernetes_api_leaves_lists_empty(sa_dir: Path) -> None:
    snap = await probe(sa_dir, api_base="https://nowhere:443").snapshot(
        ServiceStatus("account", "dev", "x", True)
    )
    assert snap.cluster is True and snap.pods == [] and snap.deployments == []


def test_admin_system_route_and_healthz_carry_version(
    client: TestClient, mailer: FakeMailer, settings: Settings
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    r = client.get("/api/account/admin/system", headers=bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"version", "commit", "cluster", "services", "pods", "deployments"}
    assert body["cluster"] is False and body["pods"] == [] and body["deployments"] == []
    assert body["services"][0] == {
        "name": "account",
        "version": settings.app_version,
        "commit": settings.app_commit,
        "healthy": True,
    }
    assert set(body["services"][1]) == {"name", "version", "commit", "healthy"}
    h = client.get("/api/account/healthz").json()
    assert h == {"status": "ok", "version": settings.app_version, "commit": settings.app_commit}


@pytest.mark.anyio
async def test_service_builds_the_response_from_the_probe(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer, sa_dir: Path
) -> None:
    service = AccountService(settings, repo, mailer, system=probe(sa_dir))
    info = await service.admin_system()
    assert info.cluster is True and len(info.pods) == 2 and len(info.deployments) == 2
    assert info.services[0].name == "account" and info.services[0].healthy is True
    assert json.loads(info.model_dump_json())["pods"][0]["service"] == "account"


def test_service_urls_drive_both_probes_and_purges() -> None:
    env = {
        "DATABASE_URL": "x",
        "AUTH_JWT_SECRET": "y",
        "PUBLIC_BASE_URL": "https://z",
        "INGEST_URL": "http://ingest.svc:8000/",
        "RAG_URL": "https://rag.svc",
        "APP_VERSION": "0.7.0",
        "APP_COMMIT": "deadbeef",
    }
    s = Settings.from_env(env)
    assert (s.ingest_url, s.rag_url) == ("http://ingest.svc:8000", "https://rag.svc")
    assert s.system_services == (
        ("ingest", "http://ingest.svc:8000/healthz"),
        ("rag", "https://rag.svc/healthz"),
    )
    assert (s.app_version, s.app_commit) == ("0.7.0", "deadbeef")
    defaults = Settings.from_env(
        {k: v for k, v in env.items() if k not in ("INGEST_URL", "RAG_URL")}
    )
    assert defaults.system_services == (
        ("ingest", "http://ingest/healthz"),
        ("rag", "http://rag/healthz"),
    )
