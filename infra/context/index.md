# Context index

Why `infra/` is built the way it is. Family-wide reasoning lives in the
repository root's `context/`.

## 0

## 1

## 2

## 3

## 4

## 5

## 6

## 7

## 8

## 9

## A

## B

## C

- [cluster.md](cluster.md) — one Helm chart for application and platform, autoscaled replicas and worker Deployments, layered rate limiting, committed production values file, one Secret per concern, generated secrets (the voucher key never rotated), CPU and memory requests from measured use, account's own ServiceAccount with a read-only Role, the client address from the load balancer's PROXY protocol header, read-only root filesystems with a /tmp emptyDir and digest-pinned Job images, ingress-only NetworkPolicies with one policy per service-to-service call, SHA-pinned workflow actions bumped by Dependabot, image provenance and SBOM, the Postgres suites in CI on a PostgreSQL 18 service container, the Vultr billing key in account's Secret instead of a CronJob, CHANGELOG changes checked to sit under [Unreleased], a 2760 s grace for draining rag workers; superseded: two manifest-era entries, the generated values file and the numeric-uid workaround

## D

- [database.md](database.md) — service-owned SQL migrations run as a Helm hook, the embedding dimension as a psql variable, the instance as an input with a bootstrap Job, verify-full against the project CA, trusted IPs instead of an open instance, service migrations under the application role; superseded: the open instance and all migrations as the admin role

## E

## F

## G

## H

## I

- [inference.md](inference.md) — which models on Vultr Serverless Inference, why 1024 embedding dimensions, where the prices come from, whisper-large-v3-turbo for speech to text priced per second, clef for decision outputs priced per input token, three judge models outside the qwen family mapped by rag's evaluation, all in sea

## J

## K

## L

- [local-development.md](local-development.md) — the local compose stack: RustFS instead of MinIO, the same bootstrap and migration scripts as the cluster, local-only credentials in the file

## M

## N

## O

- [object-storage.md](object-storage.md) — why storage sits in `ams` while the cluster is in `fra`, the bucket created by curl, and the cluster chosen by id

## P

- [provisioning.md](provisioning.md) — OpenTofu for the cluster and the object storage (the database is an input), kubeconfig from vultr-cli with the admin credentials in the state as well, kept for this deployment (#288)

## Q

## R

## S

## T

## U

## V

## W

## X

## Y

## Z

