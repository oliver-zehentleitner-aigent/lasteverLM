"""What the admin System page shows: the other services' health and the pods and
deployments of this namespace, read from the Kubernetes API with the pod's own
ServiceAccount (context/system.md). Read-only, short timeouts, never raises into a route.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("lasteverlm_account")

SERVICEACCOUNT_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
NAME_LABEL = "app.kubernetes.io/name"
TEMPLATE_HASH_LABEL = "pod-template-hash"  # set by the ReplicaSet controller on every pod


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    version: str | None
    commit: str | None
    healthy: bool
    dependencies: dict[str, str] | None = (
        None  # core's healthz: {"postgres"|"storage"|...: "ok"|"down"}
    )


@dataclass(frozen=True)
class PodStatus:
    name: str
    service: str
    image_tag: str | None
    ready: bool
    restarts: int
    node: str | None
    started_at: datetime | None
    phase: str | None = None  # Pending | Running | Succeeded | Failed | Unknown
    reason: str | None = None  # a container's waiting/terminated reason, null when running
    template_hash: str | None = None  # the pod-template-hash label: which ReplicaSet owns it


@dataclass(frozen=True)
class DeploymentStatus:
    name: str
    replicas: int
    ready: int
    updated: int
    progressing: bool | None = (
        None  # a rollout is under way (Progressing without NewReplicaSetAvailable)
    )
    available: bool | None = None  # the Available condition
    replica_sets: int = 0  # ReplicaSets with pods, counted from the pods' template hashes


@dataclass(frozen=True)
class SystemSnapshot:
    cluster: bool
    services: list[ServiceStatus] = field(default_factory=list)
    pods: list[PodStatus] = field(default_factory=list)
    deployments: list[DeploymentStatus] = field(default_factory=list)


def kubernetes_api_base(env: dict[str, str] | None = None) -> str | None:
    """The in-cluster API server, from the variables Kubernetes sets in every pod."""
    env = dict(os.environ) if env is None else env
    host, port = env.get("KUBERNETES_SERVICE_HOST"), env.get("KUBERNETES_SERVICE_PORT", "443")
    return f"https://{host}:{port}" if host else None


class SystemProbe:
    """Probes the other services and, inside a cluster, the Kubernetes API."""

    def __init__(
        self,
        services: Sequence[tuple[str, str]],
        *,
        api_base: str | None = None,
        serviceaccount_dir: Path = SERVICEACCOUNT_DIR,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._services = list(services)
        self._api_base = api_base
        self._sa_dir = serviceaccount_dir
        self._transport = transport
        self._timeout = timeout_seconds

    @property
    def cluster(self) -> bool:
        return self._api_base is not None and (self._sa_dir / "token").is_file()

    def _client(self, verify: str | bool = True) -> httpx.AsyncClient:
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport, timeout=self._timeout)
        return httpx.AsyncClient(verify=verify, timeout=self._timeout)

    async def snapshot(self, own: ServiceStatus) -> SystemSnapshot:
        services = [own, *await self.services()]
        if not self.cluster:
            return SystemSnapshot(cluster=False, services=services)
        pods, deployments = await self._kubernetes()
        return SystemSnapshot(cluster=True, services=services, pods=pods, deployments=deployments)

    async def services(self) -> list[ServiceStatus]:
        out = []
        async with self._client() as client:
            for name, url in self._services:
                out.append(await _probe_service(client, name, url))
        return out

    async def _kubernetes(self) -> tuple[list[PodStatus], list[DeploymentStatus]]:
        try:
            token = (self._sa_dir / "token").read_text().strip()
            namespace = (self._sa_dir / "namespace").read_text().strip()
            ca = self._sa_dir / "ca.crt"
            headers = {"Authorization": f"Bearer {token}"}
            async with self._client(verify=str(ca) if ca.is_file() else True) as client:
                pods = await client.get(
                    f"{self._api_base}/api/v1/namespaces/{namespace}/pods", headers=headers
                )
                pods.raise_for_status()
                deployments = await client.get(
                    f"{self._api_base}/apis/apps/v1/namespaces/{namespace}/deployments",
                    headers=headers,
                )
                deployments.raise_for_status()
            pod_list = [_pod(item) for item in pods.json().get("items", [])]
            return pod_list, [
                _deployment(item, pod_list) for item in deployments.json().get("items", [])
            ]
        except (OSError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("kubernetes api not readable, pods and deployments left empty: %s", exc)
            return [], []


async def _probe_service(client: httpx.AsyncClient, name: str, url: str) -> ServiceStatus:
    try:
        r = await client.get(url)
        body: Any = (
            r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        )
        healthy = r.status_code == 200 and (
            not isinstance(body, dict) or body.get("status", "ok") == "ok"
        )
        version = body.get("version") if isinstance(body, dict) else None
        commit = body.get("commit") if isinstance(body, dict) else None
        deps = body.get("dependencies") if isinstance(body, dict) else None
        return ServiceStatus(
            name,
            str(version) if version is not None else None,
            str(commit) if commit is not None else None,
            healthy,
            {str(k): str(v) for k, v in deps.items()} if isinstance(deps, dict) else None,
        )
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("service %s not healthy: %s", name, exc)
        return ServiceStatus(name, None, None, False)


def _pod(item: dict[str, Any]) -> PodStatus:
    meta, spec, status = item.get("metadata", {}), item.get("spec", {}), item.get("status", {})
    containers = spec.get("containers") or []
    image = str(containers[0].get("image", "")) if containers else ""
    tail = image.rsplit("/", 1)[-1].partition("@")[0]  # a digest-only image has no tag
    image_tag = tail.split(":", 1)[1] if ":" in tail else None
    statuses = status.get("containerStatuses") or []
    started = status.get("startTime")
    labels = meta.get("labels") or {}
    return PodStatus(
        name=str(meta.get("name", "")),
        service=str(labels.get(NAME_LABEL, "")),
        image_tag=image_tag,
        ready=bool(statuses) and all(bool(c.get("ready")) for c in statuses),
        restarts=sum(int(c.get("restartCount", 0)) for c in statuses),
        node=spec.get("nodeName"),
        started_at=datetime.fromisoformat(started.replace("Z", "+00:00")) if started else None,
        phase=status.get("phase"),
        reason=_container_reason(statuses),
        template_hash=labels.get(TEMPLATE_HASH_LABEL),
    )


RECENT_TERMINATION = timedelta(minutes=10)


def _container_reason(statuses: list[dict[str, Any]], now: datetime | None = None) -> str | None:
    """Why a container is not running: CrashLoopBackOff, ImagePullBackOff, OOMKilled, Error…
    The first container that is waiting or terminated gives the reason; a container that
    runs again but was terminated within the last ten minutes still shows that reason
    (the diagram's red), none when all run quietly."""
    now = now or datetime.now(UTC)
    for c in statuses:
        state = c.get("state") or {}
        for kind in ("waiting", "terminated"):
            reason = (state.get(kind) or {}).get("reason")
            if reason:
                return str(reason)
    for c in statuses:
        last = (c.get("lastState") or {}).get("terminated") or {}
        finished = last.get("finishedAt")
        if last.get("reason") and finished:
            ended = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
            if now - ended <= RECENT_TERMINATION:
                return str(last["reason"])
    return None


def _deployment(item: dict[str, Any], pods: list[PodStatus]) -> DeploymentStatus:
    spec, status = item.get("spec", {}), item.get("status", {})
    name = str(item.get("metadata", {}).get("name", ""))
    conditions = {str(c.get("type")): c for c in status.get("conditions") or []}
    progressing = conditions.get("Progressing")
    available = conditions.get("Available")
    # ReplicaSets with pods, without listing ReplicaSets (no extra RBAC): the pods of this
    # deployment carry one pod-template-hash per ReplicaSet; two hashes mean a rollout.
    hashes = {p.template_hash for p in pods if p.service == name and p.template_hash}
    return DeploymentStatus(
        name=name,
        replicas=int(spec.get("replicas") or 0),
        ready=int(status.get("readyReplicas") or 0),
        updated=int(status.get("updatedReplicas") or 0),
        # True only while a rollout is under way: the condition stays "True" after completion
        # with reason NewReplicaSetAvailable, which the diagram must not paint amber.
        progressing=(
            None
            if progressing is None
            else progressing.get("status") == "True"
            and progressing.get("reason") != "NewReplicaSetAvailable"
        ),
        available=None if available is None else available.get("status") == "True",
        replica_sets=len(hashes),
    )
