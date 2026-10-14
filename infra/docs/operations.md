# Operations

How to take `infra/` from a clean checkout to a running lasteverLM
deployment, and how to run it afterwards. The reasoning behind these
choices is in `context/`. All commands run in `infra/`.

## Tools

`tofu` (OpenTofu 1.6+), `helm` (3.x), `kubectl`, `vultr-cli`, `make`,
`curl`, `tar`, `python3` (3.10+). Migrations run inside the cluster,
the bucket is created with curl; nothing else is needed.

## Inputs

| Input | Where | Used by |
|---|---|---|
| `VULTR_API_KEY` | environment | `make up`, `make kubeconfig`, `make db-trust`, `make down` |
| `TF_VAR_object_storage_tier_id` (or `tofu/terraform.tfvars`) | environment | `make up`; `vultr-cli object-storage tier list` shows the ids |
| `DATABASE_ADMIN_URL` | environment; the managed instance's admin role, created by the maintainer | `make env` (derived URLs), `make db-bootstrap` |
| `PGSSLROOTCERT` | environment, path to the instance's CA file | `make secrets` (ConfigMap `lasteverlm-pg-ca`) |
| Domain, ACME e-mail, model names, `modelPrices` (JSON), embedding dimension, similarity floor, TTS model and voice, STT model, decision model, S3 endpoint, voucher credit | `chart/values-prod.yaml`, committed (`VALUES=<file>` for another deployment) | `make deploy`, `make check`, `make smoke` (default URL) |
| `TAG` (default `latest`), `REGISTRY` (default `ghcr.io/oliver-zehentleitner`), `COMMIT` (default `git rev-parse HEAD`) | make variables | `make deploy`; `TAG` and `COMMIT` also become `APP_VERSION` and `APP_COMMIT` in the ConfigMap, the build every `/healthz` and the System page report. Deploy from a checkout of `TAG` so the commit matches the images; `deploy.yml` checks out that commit itself |
| `INFERENCE_API_KEY` | environment | `make secrets` |
| `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `VISIT_HASH_SECRET` | environment, optional | `make secrets` (account seeds; without an allowlist and an admin address nobody can log in) |
| `VULTR_BILLING_API_KEY` | environment, optional; the API key of a Vultr sub-user with only the `billing` permission, created by the maintainer, never the account's `VULTR_API_KEY` | `make secrets` (account's daily fetch of pending charges and invoices; without it the finance page shows Vultr as not connected) |
| `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS` (required with a host), `SMTP_STARTTLS` (default `true`) | environment, optional | `make secrets` (account's mail configuration; without `SMTP_HOST` no Secret and no mail) |
| `DEMO_TOKEN` | environment, for `make smoke` only; the cluster's value is generated, see below | `make smoke` |

Generated, never typed: `APP_DB_PASSWORD`, `AUTH_JWT_SECRET` and
`DEMO_TOKEN` are created by `make env` with `openssl rand`, kept in
`build/cluster.env` (mode 600, ignored by Git) and go only into the
Kubernetes Secrets. No target prints them. To use the demo token from
the operator machine, copy it from `build/cluster.env` into the env
file by hand.

Keep the secrets in an env file outside the repository and load it with
`set -a; . ~/lasteverlm.env; set +a`.

## First deployment

```sh
make up          # VKE cluster and Object Storage (AUTO_APPROVE=1 skips the plan prompt); writes build/cluster.env
make kubeconfig  # build/kubeconfig; the Makefile exports KUBECONFIG for every target
make bucket      # sources bucket (private; the keys live only in the lasteverlm-s3 Secret)
make db-trust    # the managed database accepts only the node addresses and this machine
make platform    # ingress-nginx + cert-manager + metrics-server; prints the load balancer id
```

Point the domain in `chart/values-prod.yaml` at the load balancer's IP
(an A record; `vultr-cli load-balancer get <id>` shows it), then:

```sh
make db-bootstrap  # once: application role, database, pgvector (runs make secrets first)
make deploy        # make migrations + helm upgrade --install with chart/values-prod.yaml
make status
```

The managed PostgreSQL is not created here: the maintainer created it
by hand, `DATABASE_ADMIN_URL` is its admin connection string.
Everything derives from that one value, so a rotated admin password is
`make secrets` (which re-runs `make env`) and a restart of the pods.
Every connection uses `sslmode=verify-full` against the CA mounted
from the ConfigMap `lasteverlm-pg-ca`. `make db-trust` has to be
re-run after nodes are recycled; the proper fix is the VPC attachment
(`context/database.md`).

`make deploy` runs the migration hook first (see below) and then rolls
every service to `TAG`. A later `make deploy TAG=<full git sha>` is the
manual equivalent of what the release workflow does on a tag.
`docker.yml` tags every image with the full 40-character commit SHA
(and with the Git tag on a release); `make deploy` refuses a short SHA,
which would only end in `ImagePullBackOff`. `HELM_WAIT=0` returns right after the install instead of waiting for
the rollout. Before DNS and the certificate exist, the smoke test
reaches the deployment through the load balancer address:
`make smoke URL=https://<lb-ip> SMOKE_ARGS="--host $DOMAIN --insecure"`.

## The chart

`chart/` renders, for the namespace `lasteverlm`:

| Object | What |
|---|---|
| ConfigMap `lasteverlm-config` | non-secret settings from the values file |
| Deployments `account`, `ingest`, `rag` | API services, port 8000, `/healthz` probes, `envFrom` the ConfigMap and their Secrets |
| Deployments `ingest-worker`, `rag-worker` | same image, command `lasteverlm-<service>-worker`, no Service, no port |
| Deployment `web` | static frontend, port 8080 |
| HorizontalPodAutoscalers | one per Deployment above, CPU based (80 % of the request), minimum two replicas |
| Services | one per API service and web, port 80 |
| Ingress `lasteverlm` | path routing `/api/account`, `/api/ingest`, `/api/rag`, `/`; TLS via cert-manager; per-IP rate limiting (`limit-rps`, burst multiplier, `limit-connections`) |
| ClusterIssuer `letsencrypt` | ACME http01 |
| Job `lasteverlm-migrate` + ConfigMap | pre-install/pre-upgrade hook, see Migrations |
| NetworkPolicies `default-deny-ingress`, `from-ingress-controller`, `account-health-probes`, `rag-to-ingest` | no pod accepts a connection except from the `ingress-nginx` namespace (any port, including cert-manager's HTTP-01 solver), on the API port from `account` (the System page's health probes), and on ingest's API port from `rag` and `rag-worker` (sources read when used, the agent chat's steps); egress is open |
| ServiceAccount `account`, Role and RoleBinding `account-kubernetes-read` | `get`/`list` on `pods` and `apps/deployments` in this namespace only; the `account` pods mount the token (`automountServiceAccountToken: true`) for the admin System page |

Values: `chart/values.yaml` holds the defaults (replicas, autoscaler
bounds, resources, rate limits, which Secrets each service mounts).
Every image sets a numeric `USER`; an image that names its user would
need `runAsUser` in its values, because `runAsNonRoot` cannot verify a
name. Every container runs with `readOnlyRootFilesystem`, no
privilege escalation, all capabilities dropped and the `RuntimeDefault`
seccomp profile; `/tmp` is the only writable path, an `emptyDir` of
`tmpSizeLimit` (256 MiB; a pod above it is evicted). Only `account`
mounts a ServiceAccount token, every other pod has
`automountServiceAccountToken: false`. The migration Job runs the
`postgres` image pinned by digest as its `postgres` user (uid 70), with
its own resources.
The readiness and liveness probes call `/healthz`, which answers `ok`
while the process serves requests; the state of the dependencies
(`postgres`, `storage`, `inference`: `ok` or `down`) is in its body and
on Admin > System, not in the status. An outage of the database, the
object storage or the inference platform therefore neither restarts the
pods nor takes them out of their Service: every replica is affected the
same way, and the requests that need the dependency fail while the rest
keep working. During an outage, read the System page, not pod restarts.
(Before, `account`'s `/healthz` pinged the database, so a database
outage made its probes fail and restarted its pods.)
VKE's CNI is Calico, which enforces the NetworkPolicies;
`networkPolicy.enabled: false` removes them. Check after a deploy:
`kubectl -n lasteverlm run np-check --rm -i --restart=Never --image=busybox:1.37 -- wget -qO- -T 3 http://rag/healthz`
must time out, and the site and the System page must still work.
`kubernetesRead: true` on a service (only `account`) renders its
ServiceAccount, Role and RoleBinding from `templates/rbac.yaml`; without
them the System page still loads, with empty pod and deployment lists.
Check the grant after a deploy:
`kubectl -n lasteverlm auth can-i list deployments.apps --as=system:serviceaccount:lasteverlm:account`
(`yes`; the same for `pods`, and `no` for any verb other than `get` and `list`).
`chart/values-prod.yaml` holds the deployment-specific part (domain,
ACME e-mail, model names, prices, embedding dimension, TTS voice, S3
endpoint, voucher credit), committed and changed by pull request; `make deploy` passes
it to Helm with the image tag and registry from `TAG` and `REGISTRY`.
The chart fails the render when `modelPrices` is not valid JSON. After
`make up` in a new region, put the `s3_endpoint` tofu output into the
file. The chart version
is the repository tag: `make package VERSION=0.1.0`.

## Migrations

`make migrations` collects `db/migrations/*.sql` from `infra/`
(extensions, applied first) and from `../core`, `../account`,
`../ingest`, `../rag`, in that order, into `chart/files/migrations.tgz`
next to a copy of `db/migrate.sh`. The chart ships both as a ConfigMap
and runs the script in a `postgres:17-alpine` Job as a Helm
pre-install/pre-upgrade hook with the admin connection string. A failed
migration fails the release before any pod changes.

Contract for the service directories:

- Files are `db/migrations/NNNN_<topic>.sql`, numbered per service, applied in file order.
- Each file runs in its own transaction and is recorded as `<service>/NNNN_<topic>` in `schema_migrations`; never edit an applied file, add a new one.
- The psql variable `:EMBEDDING_DIMENSION` is available (default 1536), so `vector(:EMBEDDING_DIMENSION)` follows the configured provider.
- `CREATE EXTENSION` belongs in `infra/db/migrations`, not in a service's migration.
- Service files run under `SET ROLE lasteverlm` (the application role owns its tables; the admin is a member of that role, granted by `make db-bootstrap`). A migration must not assume superuser rights or ownership of anything the application role does not own.

To see what a run did: `kubectl -n lasteverlm logs job/lasteverlm-migrate`
(the Job is deleted on success and before the next run).

## Secrets

| Secret | Keys | Mounted by |
|---|---|---|
| `lasteverlm-db` | `DATABASE_URL` (application role) | account, ingest, rag and their workers |
| `lasteverlm-db-admin` | `DATABASE_URL` (admin role, application database) | migration Job only |
| `lasteverlm-db-bootstrap` | `DATABASE_ADMIN_URL`, `APP_DB_PASSWORD` | bootstrap Job only |
| ConfigMap `lasteverlm-pg-ca` | `pg-ca.crt` | every pod that opens a database connection, at `/etc/lasteverlm/pg-ca.crt` |
| `lasteverlm-s3` | `S3_ACCESS_KEY`, `S3_SECRET_KEY` | ingest, rag (audio files) |
| `lasteverlm-inference` | `INFERENCE_API_KEY` | ingest, rag |
| `lasteverlm-auth` | `AUTH_JWT_SECRET`, `DEMO_TOKEN` | account, ingest, rag |
| `lasteverlm-account` | `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `VISIT_HASH_SECRET`, `VOUCHER_KEY`, `VULTR_BILLING_API_KEY` (empty when not set) | account |
| `lasteverlm-smtp` (optional) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` | account |

Re-running `make secrets` updates the objects in place; pods pick the
new values up on their next restart (`kubectl -n lasteverlm rollout restart deployment`).

`VOUCHER_KEY` (32 random bytes, standard base64) encrypts the voucher
codes account keeps so an admin can show and resend them; account
refuses to start without a valid one. `make env` generates it once and
keeps it in `build/cluster.env` like `AUTH_JWT_SECRET`. Never replace
it: with a new key every stored code is unrecoverable (the vouchers stay
redeemable, showing and sending them fails), and there is no
re-encryption. Losing `build/cluster.env` loses it too; the live value
is in the Secret.

`VULTR_BILLING_API_KEY` lets account read Vultr's pending charges and
invoices once a day for the finance page. Create a sub-user in the
Vultr console with API access and the `billing` permission only, put
its API key into the env file, run `make secrets` and restart account. Never
use the account's own `VULTR_API_KEY` here: it can create and delete
every resource. Vultr's permission list has no read-only billing
variant, so the sub-user's key is narrower than the account key, not
read-only. Without the key the fetch does not run and the finance
page shows Vultr as not connected. Account reaches `api.vultr.com` on
443; egress is open (NetworkPolicies above), keep 443 outward if that
ever changes.

Mail works the same way: account reads its SMTP configuration from
`lasteverlm-smtp`. Set the `SMTP_*` values in the env file, run
`make secrets`, then `kubectl -n lasteverlm rollout restart
deployment/account`; a change of server or password is the same
rotation. Removing `SMTP_HOST` from the env file does not delete the
Secret: `kubectl -n lasteverlm delete secret lasteverlm-smtp` does.

Edge: ingress-nginx redirects HTTP to HTTPS and sends HSTS
(`platform/ingress-nginx.values.yaml`); the Ingress additionally
carries `force-ssl-redirect`. Its access log is one JSON object per
request with the path but without the query string, which for the
magic-link callback is the sign-in token.

Client address: the Vultr load balancer forwards TCP (layer 4) and
puts a PROXY protocol header in front of every connection
(`vultr-loadbalancer-proxy-protocol`); nginx reads the address from it
(`use-proxy-protocol`) and passes it on as `X-Forwarded-For` and
`X-Real-IP`, replacing whatever the client sent. That address is what
the edge rate limits count, what core's rate limiter, blocks and bans
see, and what the access log shows. `make platform` also sets the
`vultr-loadbalancer-hostname` annotation to the domain, so the Service
status carries a hostname instead of the IP and in-cluster requests to
the domain (cert-manager's HTTP-01 self check) go through the load
balancer rather than straight to nginx without the header. Both sides
change together in `make platform`; requests fail for the seconds until
the load balancer has applied the annotation. The platform is not part
of a tag deploy: a change in `platform/` is rolled out by `make
platform`. Check after a change: a request with a forged header,
`curl -H 'X-Forwarded-For: 203.0.113.9' https://<domain>/healthz`, must
appear in `kubectl -n ingress-nginx logs deploy/ingress-nginx-controller`
with the caller's real address.

## TLS certificate

cert-manager issues the certificate through the ClusterIssuer
`letsencrypt` (ACME HTTP-01, solved through the nginx ingress class,
contact `ACME_EMAIL`). The Ingress names the secret `lasteverlm-tls`;
cert-manager creates the Certificate from it, and the order stays
pending until `DOMAIN` resolves to the load balancer, then completes on
its own. For lasteverlm.zehentleitner.co that happened on 2026-10-13:
Certificate `lasteverlm-tls` Ready, issuer Let's Encrypt `YR2`, SAN
`lasteverlm.zehentleitner.co` only, valid 07:01 UTC (09:01 CEST) to
2027-01-11, renewal scheduled by cert-manager for 2026-12-12 (30 days
before expiry). Checked from outside: `http://` answers 308 to
`https://`, `https://` answers 200 with
`Strict-Transport-Security: max-age=31536000`.

```sh
kubectl -n lasteverlm get certificate,certificaterequest,order   # Ready / valid
kubectl -n lasteverlm describe certificate lasteverlm-tls         # events, renewal time
```

A Certificate that stays not Ready: `kubectl -n lasteverlm get
challenge` shows the pending HTTP-01 challenge and why (usually DNS not
pointing at the load balancer yet, or port 80 not reachable).

## Platform versions

Pinned in the `Makefile`: ingress-nginx chart 4.15.1 (controller
1.15.1), cert-manager v1.21.2, metrics-server chart 3.14.0, VKE
`v1.37.1+2` (default in `tofu/variables.tf`; `make vke-versions` lists
what the API offers). The Vultr provider is locked in
`tofu/.terraform.lock.hcl` (version and checksums for Linux and macOS,
amd64 and arm64); a bump is `tofu init -upgrade` followed by `tofu
providers lock -platform=linux_amd64 -platform=linux_arm64
-platform=darwin_amd64 -platform=darwin_arm64`. Bumps go through a pull
request and a `CHANGELOG.md` line.

`make env` reads every tofu output at once (`tofu output -json`,
`scripts/tofu_outputs.py`) and stops without touching
`build/cluster.env` when one is missing or empty: `tofu output -raw`
exits 0 and prints a warning to stdout when the state has no outputs,
which the earlier per-output calls wrote into the file as values.

## Workflows

Owned here, stored at the repository root in `.github/workflows/`:

| File | Trigger | What |
|---|---|---|
| `ci.yml` | push, pull request, path-filtered per directory | `make check` in the directories that changed; for core, account, ingest and rag also the Postgres suite (`tests/test_postgres.py`) against a `pgvector/pgvector` PostgreSQL 18 service container, failing on any skipped test |
| `docker.yml` | push to `main`, tags `v*` | builds every service image with the repository root as context (`-f <service>/Dockerfile .`), pushes to ghcr.io tagged with the Git SHA and the tag; web gets `CSP_MEDIA_SRC`, the `s3Endpoint` of `chart/values-prod.yaml`, so its CSP loads images, audio and frames only from that storage origin |
| `deploy.yml` | tags `v*` (after `docker.yml`), and manual with a tag input | `make deploy TAG=<tag>` in `infra/` with the kubeconfig from a repository secret, then the smoke test where a demo token is configured |
| `ktw-lint.yml` | push to `main`, pull request | the Keep the Why structure check for the root and every sub-project |
| `pages.yml` | push to `main` | the Keep the Why dashboard export |
| `black.yml` | push to `main`, pull request | `black --check` in every Python directory |

Every workflow has a `permissions` block; only `docker.yml`
(`packages: write`) and `pages.yml` (Pages deploy) get more than
`contents: read`. Every action is pinned to a commit SHA with the
release as a comment (`@<sha> # v7.0.1`), so a moved tag cannot change
what runs next to the secrets; a bump replaces both. The one exception
is `ktw-lint.yml`'s `keep-the-why@lint-latest`, rolling on purpose
(the comment there names the pinned form). Secrets reach a `run`
step only through `env`, never as `${{ secrets.* }}` inside the
script. `docker.yml` attaches the OCI labels and annotations from
`docker/metadata-action`, a provenance attestation (`mode=max`) and an
SBOM to every image.

`deploy.yml` serializes rollouts with the concurrency group `deploy` on
its job, not on the workflow: docker runs on `main` start the workflow
too and are skipped by the job's condition, and at the workflow level
they took the group and cancelled a pending tag deploy. One pending
deploy per group remains GitHub's rule, so of two tags pushed while a
deploy runs, only the newer one rolls out.

Repository secrets for `deploy.yml`: `KUBECONFIG_B64` (the file
`make kubeconfig` writes, base64), the only one required, and
`DEMO_TOKEN` (optional; without it the smoke step is skipped). No
repository variables: the configuration comes from the committed
`chart/values-prod.yaml`, the same file `make deploy` uses on an
operator machine, and the smoke test targets the domain in it.

## Changes made by hand

Production changes outside the chart and the Makefile, each ordered by
the maintainer.

- 2026-10-14, 10:51 UTC, in one transaction through the application
  role: the 15-minute block of `91.115.8.66` (the address the VM and the
  maintainer's browser share), set by an unthrottled CSP walk, deleted
  from `ip_blocks` with its strike (1 row; no ban existed, `ip_bans`
  unchanged); the admin panel has no action for blocks, only for bans.
  The rate limiter's `per_minute` in `settings` key `ratelimit` raised
  from 120 to 240, the other rules unchanged (`block_minutes` 15,
  `ban_after_strikes` 3, `strike_window_hours` 24); core reads the row
  within 30 seconds. The admin panel shows and changes the value from
  then on.

## Teardown

`make down` runs `tofu destroy` after its confirmation prompt and
removes `build/cluster.env` and `build/kubeconfig`. The Let's Encrypt
account key and certificates go with the cluster.

## Checks

`make check` runs what CI runs for this directory: `tofu fmt` and
`validate`, `helm lint` and `helm template`, `sh -n` on the runner, `black --check`
on `scripts/` and `tests/` (line length 100 from `pyproject.toml`, as in
the services), `scripts/dburls.py`, the unit tests, `ktw-lint`. Helm
lints and renders with `chart/values-prod.yaml`.

`make web-csp-check` (needs Docker and `DEMO_TOKEN`) walks the web app in
headless Chromium and lists every Content Security Policy violation:
it builds the web image from this checkout with `CSP_MODE` (default
`report`, so the policy is sent as `Content-Security-Policy-Report-Only`
and nothing is blocked), or takes `WEB_IMAGE=<image>`, runs it read-only
in a throwaway Docker network, and drives it from the Playwright image
(pinned by digest in the `Makefile`). The page loads from the image;
its `/api` and `/shared` requests are fetched from `URL` (the live
deployment by default), so the app sees one origin as in production.
`scripts/csp/walk.mjs` signs in with the demo token, opens every
notebook and every ready output kind (mind map, audio, …), one output
a judge has read with its judge panel and source list open, `/library`,
`/settings`, every admin page including the five finance pages (the
panel renders only for an admin or viewer; the demo token is a plain
user, so these steps report "no admin panel" and count as not walked;
run with a viewer's token, `DEMO_TOKEN="$WALK_TOKEN"`, to walk the panel),
and the theme toggle,
opens one shared page per output kind and plays the audio in the
viewer and on its shared page. It prints the pages it visited, the
distinct violations (directive and blocked URL), console errors, failed
responses, every other origin the page loaded from directly (the
storage host for images and audio) and whether the audio played. A canary inline
script is injected first and must be reported, so "0 violations" cannot
come from a page without a policy. Every request to the deployment waits
for a slot, `WALK_RPS` per second (default 1): core blocks an address
for 15 minutes above 120 requests a minute and bans it after three
blocks, and the walk shares its address with everything else on the
machine (an unthrottled walk of 0.18.0 sent about 1800 requests in a few
minutes and got the VM's address blocked). The report gives the
number of requests and the rate reached. Exit 0: clean; 1: violations; 2:
the canary was not reported; 3: a storage load failed or came from
another origin. The storage step checks the narrowed policy where it
matters: on `/library` it hovers an image's name (the preview loads its
presigned image) and plays an audio source if there is one; in a
notebook it opens a ready PDF source's tab (the original in a frame) and
a ready web page source's tab (its stored snapshot in a frame whose
`sandbox` must not contain `allow-scripts` or `allow-same-origin`; no
such source fails the walk).
Each load must come from the `s3Endpoint` of the values file
(`STORAGE_ORIGIN`) and draw no violation. A build without the inline
PDF frame, or a demo user without such a source, is reported as such,
not failed. On the VM: `sg docker -c "make
web-csp-check"`. The output kinds covered are those the demo user has.

`make handbook` (needs Docker) renders `build/lasteverlm-handbook.pdf`,
the complete technical description as one document: a title page with
the latest tag and the date, a linked table of contents (no page
numbers: Chromium's print cannot resolve them; the PDF's bookmarks
carry the same entries), then `docs/project.md`,
`docs/architecture.md`, `docs/rag-pipeline.md`, `docs/ui.md`,
`rag/docs/judge-eval.md`, `infra/docs/operations.md`,
`account/docs/operations.md`, `ingest/docs/README.md`,
`core/docs/README.md` and `docs/repository-standard.md` in that order,
each as a chapter with its path. `scripts/handbook/build.mjs` turns the
Markdown into HTML with `marked` (pinned in the `Makefile`) and prints it
to A4 with page numbers in the same Playwright image as the CSP check.
The file is built from the checkout, so it is as current as the docs;
it is not committed.
