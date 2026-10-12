# Contracts

## Shared contract types are mirrored in contracts.py until the core library ships

**Id:** a354e2a0-af25-4e9c-b437-b51abd88ffdb
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12
**Revisit when:** lasteverlm-core is published

`lasteverlm_rag/contracts.py` holds the API models (Answer, Citation,
Message), the bearer-token verification and the demo user id. These are
family-wide and will come from the `lasteverlm-core` library; until that
is published the service carries a verbatim mirror, kept free of anything
service-specific, and swaps to `from lasteverlm_core import ...` on the
coordinator's signal.

**Reason:** the services are built in parallel and cannot wait for the
library, but the types must not drift between services. A mirror that is
deleted on the swap is cheaper than a temporary dependency on another
agent's unpublished branch.
