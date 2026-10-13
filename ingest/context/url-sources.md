# URL sources

## The worker fetches URLs, through a guard that only connects to public addresses

**Id:** d13f741c-2133-447b-91a7-491fa15f202b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13, for the url loader assigned on day two; maintainer review in the pull request
**Revisit when:** the cluster gets an egress policy that already blocks internal ranges for the worker, or URL sources need a proxy

A URL source is stored as the URL itself; the worker fetches it, not
the request handler. Every TCP connection, each redirect hop included,
goes through a network backend that resolves the host itself, refuses
it unless every resolved address is public, and connects to the address
it checked.

**Reason:** the worker runs inside the Kubernetes cluster, next to the
managed database, the other services and the cloud metadata endpoint
(169.254.169.254). Fetching an address a user typed is a server-side
request forgery path into all of them. Resolving and connecting in one
step closes DNS rebinding (a second, internal answer between check and
connect); checking every hop closes redirects to internal addresses.
Fetching in the worker keeps the API pods fast and lets fetch failures
use the existing retry classification.

**Alternatives:**
- Fetch in the request handler and store the page like an upload: a
  slow site holds an API request open, and a transient failure would
  need its own retry path.
- Rely on a Kubernetes NetworkPolicy for egress only: infra owns it,
  it is not in place, and a policy cannot tell the metadata endpoint
  from a public site without the same address list; worth adding as a
  second layer, not instead.
- Check the URL's host before fetching with a normal HTTP client: the
  client resolves again on connect, which is exactly the rebinding gap.
