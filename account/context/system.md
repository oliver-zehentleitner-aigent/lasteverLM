# System page

## Account reads the Kubernetes API itself, over plain HTTPS with the pod's ServiceAccount

**Id:** 5abc5d2b-1a56-4774-8ccb-3f93ccc0222a
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-13 (maintainer wanted a System page in the admin panel)
**Revisit when:** the page needs more than two list calls (watches, logs, exec), or a second service needs cluster data

`GET /admin/system` lists the namespace's pods and deployments by calling
`GET /api/v1/namespaces/<ns>/pods` and `GET /apis/apps/v1/namespaces/<ns>/deployments`
on the in-cluster API server with `httpx`: bearer token, CA certificate and
namespace from `/var/run/secrets/kubernetes.io/serviceaccount`, the server
address from the variables Kubernetes sets in every pod. Infra binds a Role
with `get`/`list` on those two resources. Without a token file the lists are
empty and the response says `cluster: false`.

**Reason, why account:** the admin panel's API is account's; it is the only
service with the admin check, and the page is an admin view like users and
stats. Giving another service an admin dependency for one read, or the web a
cluster credential, would widen the attack surface for no gain. The read is
cheap and needs no database.

**Reason, why no client library:** two GETs with a bearer token are the
whole integration. The official Kubernetes client is a large dependency with
its own configuration loading, model classes and release cadence; `httpx` is
already in the image for the service health probes, and the two JSON
documents are read with a dozen lines. The ServiceAccount files are what the
client library would read anyway.

**Rejected alternatives:** a `kubectl` subprocess in the image — rejected
because it adds a binary to a slim image and parses text; a cluster-wide
ClusterRole — rejected because the page only ever shows this namespace;
exposing the Kubernetes API through infra's web layer — rejected because it
would put a cluster credential next to the frontend.

**Consequence:** the Role is infra's; a deployment without it still serves
the page, with empty lists and one warning per request in the log.
