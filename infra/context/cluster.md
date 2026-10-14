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
`lasteverlm-auth`, optional `lasteverlm-smtp` — and each Deployment
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
**Status:** superseded
**Superseded by:** 7a8504fa-fe57-4ad7-8faf-fb722e01eedb
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

## The production configuration is a committed values file, not repository variables

**Id:** 7a8504fa-fe57-4ad7-8faf-fb722e01eedb
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family coordinator, 2026-10-13
**Revisit when:** a value in it becomes secret, or one checkout has to deploy to several environments with different values

`chart/values-prod.yaml` holds the non-secret configuration of the
production deployment: domain, ACME e-mail, model names, prices,
embedding dimension, similarity floor, TTS model and voice, S3
endpoint. `make deploy` on an operator machine and `deploy.yml` pass
the same file to Helm; only the image tag and registry come from make
variables. `deploy.yml` needs one secret, `KUBECONFIG_B64`, and
`DEMO_TOKEN` stays optional for the smoke step. The chart checks that
`modelPrices` is valid JSON, which `scripts/values.py` did before.

**Reason:** none of these values is secret and they rarely change, so
they belong versioned and reviewable in a pull request, not hidden in
repository settings; the list a maintainer has to type into GitHub
shrinks to one entry. A YAML file also keeps the JSON in
`modelPrices` away from `--set`, the reason the generated file
existed.

**Rejected alternative:** the same values as GitHub repository
variables, read by `deploy.yml` (and from the environment by
`make values` on the operator machine) — invisible in review,
typed by hand per repository, and kept in two places.

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
**Status:** superseded
**Superseded by:** none — every Dockerfile sets a numeric `USER` since main ab69bfb (2026-10-12), so the chart no longer states uids; the helper keeps honouring `runAsUser` for an image that names its user
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

## CPU requests are sized from measured use, the autoscalers target 80 %

**Id:** 14e82ec9-09aa-4642-a43a-dbf3cec84084
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** `kubectl top` on the cluster, 2026-10-13: idle and under five parallel smoke runs × 3; maintainer go relayed by the family coordinator
**Revisit when:** PDF, image or audio processing shows sustained CPU above the new requests, or the node plan changes

CPU requests: APIs (account, ingest, rag) 50m, workers 100m, web 25m,
down from 100m, 200m and 50m; memory unchanged. The autoscalers'
target rises from 70 % to 80 %.

**Reason:** at the old values the application alone requested 1500m
of the two nodes' 4000m, and the platform another ~1400m, so a rollout
of all six Deployments at once (one surge pod each) left web Pending.
Measured use was a fraction of that: 1–7m per pod idle, peaks of 29m
(ingest), 35m (ingest-worker), 16m (rag), 6m (account), 1m (rag-worker,
web) under load, 287m on the busiest node. The services mostly wait on
the remote inference API. Lower requests free 750m without a cost or a
single-replica window. Because the autoscaler's target is a percentage
of the request, ingest at 29m against 50m would sit near 70 %; 80 %
keeps that load from scaling out on its own.
Known and accepted: right after a rollout the ingest-worker autoscaler
scales out to four or six replicas for a few minutes on the start-up
CPU spike, measured against the 100m request, and returns to two by
itself; at the current headroom that is harmless, so no scale-up
stabilization window was added.

**Rejected alternatives:** a third node — 20 USD/month for headroom that
measured use does not need; `maxSurge 0` / `maxUnavailable 1` —
no cost, but each Deployment drops to one replica during a rollout;
the VKE node-pool autoscaler (min 2, max 3) — deferred, not rejected: a
node it adds gets a public IP outside the database's trusted list, so
it waits for the database's VPC attachment.

## account reads the cluster through its own ServiceAccount, not the namespace default

**Id:** ac46e922-85b8-40be-b238-994f2cbef5de
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request, 2026-10-13 (ServiceAccount, Role with get/list on pods and apps/deployments, RoleBinding, token mounted for account); the reasons below are drawn here
**Revisit when:** a second service needs cluster data, or the System page needs more than get/list (watch, logs, exec)

The chart gives a service a ServiceAccount of its own when its values
set `kubernetesRead: true` (only `account`); `templates/rbac.yaml`
binds it to a Role with `get`/`list` on `pods` and
`apps/deployments` in the release namespace, and the API Deployment
runs with that ServiceAccount and `automountServiceAccountToken: true`.

**Reason:** the grant belongs to the one pod that reads it. Every other
pod (the workers, ingest, rag, web, the migration Job) keeps the
namespace's default ServiceAccount, which has no Role.

**Rejected alternatives:** binding the Role to the namespace's
`default` ServiceAccount — one object fewer, but every pod in the
namespace could then list the deployments; a ClusterRole — the page
only shows this namespace (account's `context/system.md`, Id
5abc5d2b-1a56-4774-8ccb-3f93ccc0222a).

## The client address comes from the load balancer's PROXY protocol header, never from a request header

**Id:** 4ef95aa0-b4d0-4ede-a065-1fa2298eb58b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security audit finding relayed by the family coordinator, 2026-10-14; checked against production the same night (a request with a forged `X-Forwarded-For: 203.0.113.9` was logged as 203.0.113.9; requests without it as a node address); Vultr CCM load balancer annotations; ingress-nginx 1.15.1 template
**Revisit when:** the load balancer changes to HTTP (layer 7) forwarding, or a CDN or second proxy is put in front of it

The trust boundary for the client address is the Vultr load balancer:
it forwards TCP and puts a PROXY protocol header in front of each
connection, and nginx takes the address only from that header
(`use-proxy-protocol`). What nginx passes on as `X-Forwarded-For` and
`X-Real-IP` is that address, replacing anything the client sent; the
edge rate limits, core's rate limiter, blocks, bans and the login log
all rely on it. The Service carries the domain as
`vultr-loadbalancer-hostname`, so in-cluster requests to the domain
go through the load balancer and arrive with the header too.

**Reason:** a request header is written by whoever sends the request.
With `enable-real-ip` and its default trusted range `0.0.0.0/0`, nginx
believed every client's `X-Forwarded-For`: limits could be bypassed by
changing the header, and anyone could get a third party's address
blocked. Without the header the address was a node's, so every client
shared one rate-limit bucket. The load balancer forwards at layer 4,
so it sees the real peer and adds no header of its own; PROXY protocol
is how it hands that peer over, and only the load balancer can write it.

**Rejected alternatives:** `enable-real-ip` with `proxy-real-ip-cidr`
limited to the load balancer's addresses: the layer-4 load balancer
adds no `X-Forwarded-For`, so it would have yielded the load balancer's
address, not the client's. `externalTrafficPolicy: Local`: keeps the
source address only for traffic that is not proxied, and the Vultr load
balancer is a proxy. Keeping `0.0.0.0/0`: rejected, it is the finding.

**Consequence:** a PROXY protocol change has to switch both sides
together (`make platform` does), and requests fail for the moment
between nginx switching and the load balancer applying the annotation.
Without the hostname annotation, kube-proxy sends in-cluster requests to
the load balancer IP straight to nginx without the header, and
cert-manager's HTTP-01 self check fails at the next renewal.

## Containers run with a read-only root filesystem, /tmp as a size-limited emptyDir, and digest-pinned Job images

**Id:** 9dbb3d60-c8c8-41e7-b480-723195c58c9d
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** infra security audit requested by the maintainer through the family coordinator, 2026-10-14; read-only behaviour tested on the local stack the same night; the reasons are drawn here
**Revisit when:** a service needs to write outside /tmp (a cache, a model download), an upload larger than the /tmp limit has to be buffered, or the postgres image gets a numeric USER

Every container (API services, workers, web, the migration Job, the
bootstrap Job) sets `readOnlyRootFilesystem`, the `RuntimeDefault`
seccomp profile, no privilege escalation and no capabilities. `/tmp` is
an `emptyDir` limited to `tmpSizeLimit` (256 MiB), the migration Job
unpacks into its own `emptyDir` `/work`. The `postgres` image of both
Jobs is pinned by digest and runs as uid 70, its `postgres` user.

**Reason:** a process that is taken over cannot replace code or drop a
tool into the image's filesystem, and the syscalls outside the
container runtime's default profile are gone. The services write only
what Starlette spools for an upload above 1 MB, which goes to the
temporary directory; the local stack ran `make local-smoke` with every
service read-only and only `/tmp` writable, and the migration and
bootstrap scripts ran as uid 70 on a read-only root. The size limit
makes a runaway temp file evict its own pod instead of filling the
node's disk. The Jobs ran `postgres:18-alpine` as root under a moving
tag; the migration Job holds the admin connection string, so it gets the
most fixed image and the least privilege.

**Rejected alternatives:** `/tmp` as a memory-backed `emptyDir` — counts
against the pod's memory limit, and an upload spool would compete with
the worker's PDF rendering; leaving the Jobs on the moving tag — a
silent image change in the one container that runs DDL as admin.

## NetworkPolicies restrict ingress; egress stays open

**Id:** 4091a506-e9a2-4803-bfe0-f48fc113d632
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** infra security audit requested by the maintainer through the family coordinator, 2026-10-14; the CNI read from the cluster (calico-node DaemonSet); the policy shape and the egress reasoning are drawn here
**Revisit when:** a policy engine with domain-based egress rules is installed, the managed database gets a VPC address, or a service starts calling another one directly

The chart denies every incoming connection in the namespace except
from the `ingress-nginx` namespace (any pod, any port) and, on the API
port, from `account` to the API services. Nothing restricts egress.

**Reason, ingress:** core trusts the `X-Forwarded-For` nginx sets, and
the edge rate limits live in nginx; a pod that reached a service
directly would bypass both. No service calls another over HTTP except
account's health probes; the services share data through the database.
The controller's namespace is allowed on every port because
cert-manager's HTTP-01 solver pods run in this namespace on their own
port and are reached through nginx.

**Reason, egress open:** every outbound destination is an external
host named by DNS — Object Storage, Serverless Inference, the SMTP
server, the managed database (public address, VPC attachment pending),
the Vultr API for account's billing read — and Kubernetes NetworkPolicy matches only IP blocks and ports. An
egress policy would come down to "DNS, 443, 587 and the database port to
anywhere", which blocks little and breaks on the next port a provider
uses.

**Rejected alternatives:** per-service policies naming each caller
(nginx only to web, account, ingest, rag) — the controller already
reaches nothing but the Ingress backends, so it adds objects without
closing a path; a port-based egress allowlist — see above.

## Workflow actions are pinned by commit SHA; images carry provenance and an SBOM

**Id:** 4408c83d-3036-4b90-8cd2-a9dec926e165
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** infra security audit requested by the maintainer through the family coordinator, 2026-10-14; the reasons are drawn here
**Revisit when:** an automatic updater for action pins is enabled (then the bump path changes), or GitHub offers immutable action releases that every action used here adopts

Every `uses:` in `.github/workflows/` names a commit SHA with the
release as a comment; the exception is the rolling
`keep-the-why@lint-latest` in `ktw-lint.yml`, from the maintainer's own
repository and documented in place. `docker.yml` pushes every image
with a provenance attestation (`mode=max`), an SBOM and the OCI
annotations.

**Reason:** a tag is a pointer its owner can move. `deploy.yml` runs
next to the cluster's kubeconfig and `docker.yml` with a token that
can push images; a moved tag in a third-party action would run new
code there without a change in this repository. A SHA cannot move. The
provenance and the SBOM let a reviewer check which commit and which
build an image in the registry came from and what is inside it, without
access to the build logs.

**Rejected alternatives:** pinning only the third-party actions and
leaving `actions/*` on major tags — the same risk class with fewer
owners, and a mixed rule is easier to get wrong; adding Dependabot for
the pins in the same change — it opens pull requests on its own, which
is the maintainer's call, so it is proposed separately.

## CI runs the Postgres suites against a PostgreSQL 18 service container, not through the directories' Docker targets

**Id:** 30aca51a-5d54-4a6f-8e87-da589f31476e
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** audit finding relayed by the family coordinator, 2026-10-14 (the suites never ran in CI); image choice confirmed by the coordinator the same night; the reasons are drawn here
**Revisit when:** the managed instance moves to another major version, or a directory's suite needs more than one empty database

The `python` job of `ci.yml` has a `pgvector/pgvector:0.8.7-pg18-trixie`
service container per matrix entry. After `make check` it runs the
directory's `tests/test_postgres.py` with the connection string in the
variable that directory reads, and fails when a test is skipped.

**Reason:** the suites test the SQL the services run in production
(migrations, atomic updates, vector queries) and were only run by hand.
A service container is ready (health check) before the first step and
is discarded with the job, so every suite starts on an empty database.
PostgreSQL 18 because production runs 18; the directories' own targets
default to a 17 image. The skip check exists because every suite skips
itself without its variable, which would turn a renamed variable into
a green run.

**Rejected alternatives:** calling each directory's `make test-postgres`
with Docker on the runner — the targets start their own container, so
the CI image choice would be a per-directory override, and their
`DOCKER ?= sg docker -c` default does not work on a runner;
`pgvector/pgvector:pg17` as first proposed — a different major than
production.

## The Vultr billing key lives in account's Secret, not in a separate CronJob

**Id:** e53ac516-3186-4096-bfd2-727f4136f426
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the maintainer's go for a finance view with Vultr's pending charges and invoices, 2026-10-14, relayed by the family coordinator; the choice between a CronJob and a task in account made by account's maintainer agent the same day; the permission list read from `vultr-cli user create --help`
**Revisit when:** account's egress is restricted, the finance fetch moves out of account, or Vultr offers a read-only billing permission

`VULTR_BILLING_API_KEY` is optional in `lasteverlm-account`; account
fetches once a day in its own process. The key belongs to a sub-user
with only the `billing` permission, never the account key that
`make up` uses.

**Reason:** a CronJob of its own would have kept the key out of the
account pods and allowed an egress policy for just that job, but it
cannot write to the database without a new internal write endpoint on
account and a second token for it, which is more attack surface than the
key. The account pods already hold more sensitive values (`VOUCHER_KEY`,
`AUTH_JWT_SECRET`, the database URL). Account's writes are idempotent
upserts, so two replicas running the task cost one extra API call.

**Rejected alternatives:** a CronJob with its own Secret and egress
limited to DNS and 443 outside the cluster (above); pinning egress to
`api.vultr.com`'s addresses — NetworkPolicy matches only IP blocks, a
pinned address breaks silently when it changes; domain-based egress
policies — the cluster's CNI is Calico, which would need a platform
change for one job.

**Known risks:** Vultr's `billing` permission is the only billing
permission in the list, with no read-only variant, so the key is
narrower than the account key but not read-only.
