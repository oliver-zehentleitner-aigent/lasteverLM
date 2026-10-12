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

## Rate limiting is layered: per-IP at the ingress, blocks and bans in the services

**Id:** ebb35afa-f816-4977-b79a-bb81094e297e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family coordinator, 2026-10-12
**Revisit when:** the edge limits fire on legitimate traffic (uploads from one office), or the controller is replaced

The Ingress carries ingress-nginx's `limit-rps`,
`limit-burst-multiplier` and `limit-connections` annotations
(values in the chart) as the coarse layer: it caps what any one address
can send before a request reaches a pod. The fine layer — per-user
limits, temporary blocks, bans — is a middleware in the core library,
where the user is known. The controller writes its access log as JSON
(`platform/ingress-nginx.values.yaml`) so both layers can be read with
the same tools.

**Reason:** the edge layer needs no code and protects the services
from a flood they would otherwise have to absorb; the application layer
knows identities, credits and history, which the edge never will. Each
layer does what only it can.

**Rejected alternative:** all limiting in the application — simpler to
reason about in one place, rejected because by then every request has
already cost a pod and a database connection.


## Platform components are applied as pinned upstream manifests, not Helm charts

**Id:** 14fcc33f-ab6c-4af2-9b0d-d7d611a9d09c
**Type:** decision
**Status:** superseded
**Superseded by:** 658c9993-d0a0-40a2-abf6-7a02a4c330c2
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12
**Revisit when:** a component needs values the upstream manifest does not expose, or a third component joins

ingress-nginx and cert-manager are installed with `kubectl apply` of the
release manifests their projects publish, at versions pinned in the
`Makefile`.

**Reason:** the operator toolchain stays at `tofu`, `kubectl`,
`vultr-cli` and `make`; both components run with their defaults, so a
chart would add a templating layer with nothing to template. Pinning in
one place keeps the versions reviewable in a diff.

**Rejected alternative:** Helm — the usual path and the right one once
values need overriding, rejected because it would be the only reason to
install Helm and would add release state to manage.

## Domain, ACME e-mail and registry host are substituted into the manifests by the Makefile

**Id:** dec25659-4f61-4d6e-af03-af8d42ad992f
**Type:** decision
**Status:** superseded
**Superseded by:** 6d81fc15-6bae-4e67-960d-8f6a34a3f640
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12
**Revisit when:** more than these three values differ between deployments

`k8s/ingress.yaml` and `k8s/cluster-issuer.yaml` carry the tokens
`__DOMAIN__` and `__ACME_EMAIL__`, the Deployments carry `__REGISTRY__`
in their image names; `make deploy` copies `k8s/` to `build/k8s/`,
replaces them from the environment, and applies the rendered copy. The committed manifests stay valid YAML that
`kubectl kustomize` builds in `make check`.

**Reason:** exactly three values are deployment-specific, and all are
public. The registry host is a token rather than a fixed string because
the choice between ghcr.io and Vultr Container Registry is still open
in the parent's `context/`; the manifests must not pre-empt it. A visible `sed` on a copy is easier to audit than a templating
engine, and the rendered output is kept in `build/` for inspection.

**Rejected alternatives:** Kustomize replacements or a per-environment
overlay — correct, but an overlay per domain for two strings is more
structure than the project has environments; Helm — see the entry
above.

## One Secret per concern, one ConfigMap for the rest

**Id:** cab5ab11-63c0-47b1-8c19-78e7259ecd40
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12
**Revisit when:** a service needs a secret none of the groups covers

Secrets are split by what they unlock — `lasteverlm-db`,
`lasteverlm-db-admin`, `lasteverlm-s3`, `lasteverlm-inference`,
`lasteverlm-auth`, optional `lasteverlm-smtp-seed` — and each Deployment
mounts only the ones its service uses; non-secret settings sit in the
ConfigMap `lasteverlm-config` that every API service gets. `make secrets`
builds all of them from the OpenTofu outputs and the environment with
`--dry-run=client | kubectl apply`, so re-running it updates in place.

**Reason:** the web pod should never see the database URL, the rag
service never the S3 keys, and the admin database URL exists only for
the migration Job. One Secret per concern makes that a matter of which
`secretRef` lines a Deployment lists, visible in review.

**Rejected alternative:** one Secret with every variable, mounted
everywhere — fewer kubectl calls, rejected because it gives each pod
credentials it has no use for.

## Deployment-specific values come from a generated values file, not from --set

**Id:** 6d81fc15-6bae-4e67-960d-8f6a34a3f640
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12
**See:** cluster.md#domain-acme-e-mail-and-registry-host-are-substituted-into-the-manifests-by-the-makefile — dec25659-4f61-4d6e-af03-af8d42ad992f — as of 2026-10-12
**Revisit when:** the values stop being derivable from the environment plus the tofu outputs

`make values` runs `scripts/values.py`, which reads the environment and
the tofu outputs and prints the chart values as JSON (valid YAML) into
`build/values.yaml`; `make deploy` passes that file to Helm. The chart
itself holds only defaults.

**Reason:** `MODEL_PRICES` is a JSON string with commas and braces,
which `helm --set` parses as its own list and map syntax; a values
file side-steps that, and a generated one keeps a single source for
what is deployed, inspectable in `build/`.

**Rejected alternative:** `--set` and `--set-string` flags assembled in
the Makefile — worked until the first JSON value and would have needed
escaping rules nobody wants to maintain.

## Application secrets are generated on the operator machine, never typed

**Id:** ac3fbdfc-e603-488f-b8a2-0e1216cacdad
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer requirement relayed by the family coordinator, 2026-10-12
**Revisit when:** a secret has to be shared with a system outside the cluster (then it needs a store, not a file)

`make env` generates `APP_DB_PASSWORD`, `AUTH_JWT_SECRET` and
`DEMO_TOKEN` with `openssl rand` the first time, keeps them across
re-runs in `build/cluster.env` (mode 600, ignored by Git), and no
target prints them. `make secrets` is the only place they go from
there: into the Kubernetes Secrets. Rotation is deleting the line and
running `make secrets` again.

**Reason:** a value nobody typed cannot be weak and cannot be in a
shell history; keeping it in one ignored file makes rotation a
one-liner and keeps the Makefile free of hardcoded values.

**Rejected alternative:** a secrets manager (Vault, SOPS) — right for
a team, more than one operator and one cluster need tonight.

## The chart states each image's numeric uid because the images name their user

**Id:** b9ed80e7-d333-4473-b617-85acc51a4af6
**Type:** workaround
**Status:** active
**Evidence:** confirmed
**Source:** first deploy on 2026-10-12: every pod failed with "container has runAsNonRoot and image has non-numeric user (app)"; uids read from the images
**Revisit when:** the Dockerfiles use numeric `USER` lines, then `runAsUser` leaves the values

`runAsNonRoot: true` makes the kubelet verify the uid before start; an
image whose `USER` is a name (`app`, `nginx`) cannot be verified and the
container never starts. `chart/values.yaml` therefore carries
`runAsUser: 10001` for the Python services and `101` for web, read from
the images' `/etc/passwd`. The clean fix is `USER 10001:10001` in each
Dockerfile, which belongs to the service owners; the runtime contract
should say numeric.

**Rejected alternative:** dropping `runAsNonRoot` — would start the
pods tonight and silently allow a future image to run as root.
