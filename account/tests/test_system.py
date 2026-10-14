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
                "labels": {"app.kubernetes.io/name": "account", "pod-template-hash": "7d9f"},
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "ghcr.io/x/lasteverlm-account:0.6.0"}],
            },
            "status": {
                "phase": "Running",
                "startTime": "2026-10-13T08:00:00Z",
                "containerStatuses": [{"ready": True, "restartCount": 2, "state": {"running": {}}}],
            },
        },
        {
            "metadata": {
                "name": "account-8e0a-xyz",
                "labels": {"app.kubernetes.io/name": "account", "pod-template-hash": "8e0a"},
            },
            "spec": {"containers": [{"image": "ghcr.io/x/lasteverlm-account:0.7.0"}]},
            "status": {
                "phase": "Pending",
                "containerStatuses": [
                    {
                        "ready": False,
                        "restartCount": 0,
                        "state": {"waiting": {"reason": "ImagePullBackOff"}},
                    }
                ],
            },
        },
        {
            "metadata": {
                "name": "rag-1",
                "labels": {"app.kubernetes.io/name": "rag", "pod-template-hash": "aaaa"},
            },
            "spec": {"containers": [{"image": "registry/lasteverlm-rag@sha256:abc"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "ready": False,
                        "restartCount": 5,
                        "state": {"terminated": {"reason": "OOMKilled", "exitCode": 137}},
                    }
                ],
            },
        },
    ]
}
DEPLOYMENTS = {
    "items": [
        {
            "metadata": {"name": "account"},
            "spec": {"replicas": 2},
            "status": {
                "readyReplicas": 2,
                "updatedReplicas": 2,
                "conditions": [
                    {"type": "Available", "status": "True"},
                    {"type": "Progressing", "status": "True", "reason": "ReplicaSetUpdated"},
                ],
            },
        },
        {
            "metadata": {"name": "rag"},
            "spec": {"replicas": 1},
            "status": {
                "readyReplicas": 0,
                "conditions": [
                    {"type": "Available", "status": "False"},
                    {"type": "Progressing", "status": "True", "reason": "NewReplicaSetAvailable"},
                ],
            },
        },
    ]
}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "ingest":
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "version": "0.6.0",
                "commit": "abc1234",
                "dependencies": {"postgres": "ok", "storage": "down"},
            },
        )
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
    assert (a.phase, a.reason, a.template_hash) == ("Running", None, "7d9f")
    rolling = pods["account-8e0a-xyz"]
    assert (rolling.phase, rolling.reason, rolling.ready) == ("Pending", "ImagePullBackOff", False)
    r = pods["rag-1"]
    assert (r.image_tag, r.ready, r.node, r.started_at) == (None, False, None, None)
    assert (r.phase, r.reason, r.restarts) == ("Running", "OOMKilled", 5)
    assert [(d.name, d.replicas, d.ready, d.updated) for d in snap.deployments] == [
        ("account", 2, 2, 2),
        ("rag", 1, 0, 0),
    ]
    account_dep, rag_dep = snap.deployments
    assert (account_dep.progressing, account_dep.available, account_dep.replica_sets) == (
        True,
        True,
        2,  # two template hashes among its pods: a rollout is under way
    )
    assert (rag_dep.progressing, rag_dep.available, rag_dep.replica_sets) == (False, False, 1)
    ingest = snap.services[1]
    assert ingest.dependencies == {"postgres": "ok", "storage": "down"}
    assert snap.services[2].dependencies is None  # unreachable rag reports nothing


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
        "dependencies": {},  # the memory repository has no postgres to probe
    }
    assert set(body["services"][1]) == {"name", "version", "commit", "healthy", "dependencies"}
    h = client.get("/api/account/healthz").json()
    assert {k: v for k, v in h.items() if k != "dependencies"} == {
        "status": "ok",
        "version": settings.app_version,
        "commit": settings.app_commit,
    }
    assert h.get("dependencies") in (None, {})  # nothing to probe on the memory repository


@pytest.mark.anyio
async def test_service_builds_the_response_from_the_probe(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer, sa_dir: Path
) -> None:
    service = AccountService(settings, repo, mailer, system=probe(sa_dir))
    info = await service.admin_system()
    assert info.cluster is True and len(info.pods) == 3 and len(info.deployments) == 2
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


def test_recent_termination_still_shows_its_reason() -> None:
    from datetime import UTC, datetime

    from lasteverlm_account.system import _container_reason

    now = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    recent = [
        {
            "state": {"running": {}},
            "lastState": {
                "terminated": {"reason": "OOMKilled", "finishedAt": "2026-10-14T11:55:00Z"}
            },
        }
    ]
    old = [
        {
            "state": {"running": {}},
            "lastState": {
                "terminated": {"reason": "OOMKilled", "finishedAt": "2026-10-14T09:00:00Z"}
            },
        }
    ]
    assert _container_reason(recent, now) == "OOMKilled"
    assert _container_reason(old, now) is None
    assert _container_reason([{"state": {"running": {}}}], now) is None
    assert _container_reason([{"state": {"waiting": {"reason": "CrashLoopBackOff"}}}], now) == (
        "CrashLoopBackOff"
    )


@pytest.mark.anyio
async def test_dependency_states_reach_healthz_and_the_system_page(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer
) -> None:
    from lasteverlm_core import DependencyProbe

    async def down() -> None:
        raise RuntimeError("connection refused")

    async def up() -> None:
        return None

    probe = DependencyProbe({"postgres": down, "storage": up})
    service = AccountService(settings, repo, mailer, system=probe_system(), dependencies=probe)
    info = await service.admin_system()
    assert info.services[0].healthy is True  # the process answers
    assert info.services[0].dependencies == {"postgres": "down", "storage": "ok"}


def probe_system() -> SystemProbe:
    return SystemProbe([], transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
