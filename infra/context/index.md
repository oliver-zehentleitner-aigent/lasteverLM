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

- [cluster.md](cluster.md) — one Helm chart for application and platform, autoscaled replicas and worker Deployments, layered rate limiting, committed production values file, one Secret per concern, generated secrets, numeric uids as a workaround, CPU requests from measured use, account's own ServiceAccount with a read-only Role, the client address from the load balancer's PROXY protocol header; superseded: two manifest-era entries and the generated values file

## D

- [database.md](database.md) — service-owned SQL migrations run as a Helm hook, the embedding dimension as a psql variable, admin versus application role, the instance as an input with a bootstrap Job, verify-full against the project CA, trusted IPs instead of an open instance, service migrations under the application role

## E

## F

## G

## H

## I

- [inference.md](inference.md) — which models on Vultr Serverless Inference, why 1024 embedding dimensions, where the prices come from

## J

## K

## L

- [local-development.md](local-development.md) — the local compose stack: RustFS instead of MinIO, the same bootstrap and migration scripts as the cluster, local-only credentials in the file

## M

## N

## O

- [object-storage.md](object-storage.md) — why storage sits in `ams` while the cluster is in `fra`, the bucket created by curl, and the cluster chosen by id

## P

- [provisioning.md](provisioning.md) — OpenTofu for the Vultr resources, kubeconfig from vultr-cli

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

