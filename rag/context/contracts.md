# Contracts

## Shared contract types are mirrored in contracts.py until the core library ships

**Id:** a354e2a0-af25-4e9c-b437-b51abd88ffdb
**Type:** constraint
**Status:** superseded
**Superseded by:** 95b8ec66-e5a8-41af-b9e6-95b343c74c1c
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12

`lasteverlm_rag/contracts.py` held the API models (Answer, Citation,
Message), the bearer-token verification and the demo user id. These are
family-wide and were to come from the `lasteverlm-core` library; until it
landed the service carried a verbatim mirror, kept free of anything
service-specific, and swapped to `from lasteverlm_core import ...` on the
coordinator's signal (which happened the same day; the mirror is deleted).

**Reason:** the services are built in parallel and cannot wait for the
library, but the types must not drift between services. A mirror that is
deleted on the swap is cheaper than a temporary dependency on an
unreleased library.

## Ids and timestamps stay strings inside the service; core's models parse them at the boundary

**Id:** 95b8ec66-e5a8-41af-b9e6-95b343c74c1c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation session, 2026-10-12
**Revisit when:** the store returns typed rows, or a second service needs the internal shapes

Core's contract models carry `UUID` and `datetime` fields. Inside this
service the store returns ids as text and timestamps as whatever psycopg
hands over, the internal dataclasses keep them as strings, and the
contract models are built with `model_validate` from those strings;
core's `has_credit`, `admin_role` and `record_usage` get a `UUID` cast
at the call.
Citations are stored in `messages.citations` as JSON-mode dumps so the
column holds plain strings.

**Reason:** the swap from the local mirror to core touched every file
that names a model; keeping the internal representation as it was limited
the change to the boundary and kept the tests' fixtures readable. Pydantic
does the parsing either way, so nothing is lost on the wire.

**Rejected alternative:** `UUID` and `datetime` everywhere inside the
service. Cleaner on paper, rejected for now as a rewrite of the store,
the fakes and every assertion for no observable difference.
