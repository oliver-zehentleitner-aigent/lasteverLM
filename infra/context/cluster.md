# Cluster

## The application is one Helm chart, and the platform components are Helm charts too

**Id:** 658c9993-d0a0-40a2-abf6-7a02a4c330c2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family coordinator, 2026-10-12; the platform-side consequence drawn here the same day
**See:** cluster.md#platform-components-are-applied-as-pinned-upstream-manifests-not-helm-charts — 14fcc33f-ab6c-4af2-9b0d-d7d611a9d09c — as of 2026-10-12
**Revisit when:** the chart has to be split (a service released on its own cadence), or Helm leaves the toolchain

Everything the application needs in the cluster — ConfigMap, the four
API and worker Deployments, Services, autoscalers, Ingress,
ClusterIssuer and the migration hook — is one chart at `chart/`, whose
version is the repository tag; a tag `v*` builds the images and runs
`helm upgrade --install`. With Helm in the toolchain anyway,
ingress-nginx, cert-manager and metrics-server are installed from their
own charts at pinned versions with small values files under
`platform/`, which replaces the `kubectl apply` of upstream manifests.

**Reason:** the maintainer wants one versioned, parameterized unit per
release instead of rendered manifests, and a chart is the standard way
a reviewer expects that to look. Once Helm is required for the
application, the earlier argument against it for the platform
components ("the only reason to install Helm") is gone, and the
ingress-nginx chart exposes the controller ConfigMap (JSON access log)
as a value, which with raw manifests needed a patch after install.

**Rejected alternative:** keep Kustomize with the three rendered tokens
— fewer concepts, rejected because per-service replica and autoscaler
values, the worker Deployments and the migration hook would have made
the `sed` layer grow into a template engine of its own.

## Every API service runs at least two replicas with an autoscaler; ingest and rag get a worker Deployment

**Id:** dfef9ab1-fb55-46e7-a159-36aa634a36ce
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family coordinator, 2026-10-12
**Revisit when:** the first load test shows where the pods actually saturate, or the queue moves out of Postgres

Each API service and web is a Deployment with a
`HorizontalPodAutoscaler` (CPU utilisation, minimum two, maximum four
to six), so the replica count is owned by the autoscaler, not the
chart. ingest and rag additionally run a second Deployment from the
same image with the worker entrypoint, which claims jobs from Postgres,
scaled by its own autoscaler. metrics-server is installed because the
autoscalers need it and VKE does not ship one.

**Reason:** two replicas remove the single pod as a point of failure
during rollouts and node recycling; separating the request path from
the processing path lets uploads and generation scale on their own
load and keeps a long parse from starving the API. CPU is the one
metric every pod exposes without instrumentation, which is why the
autoscalers start there.

**Rejected alternative:** one replica per service with the in-process
background task of architecture v1 — enough for a demo, rejected by the
maintainer because horizontal scaling is one of the things the project
is meant to show. A queue outside Postgres (Redis, RabbitMQ) was not
taken: the job table is already there and one fewer stateful component
is one fewer thing to run.

