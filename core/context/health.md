# Health

## Build labels in /healthz default to "unknown", and each service keeps its route

**Id:** 0caca2a2-d80f-4532-8fb1-feeb33661453
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the coordinator's spec for the admin system page, 2026-10-13 (`APP_VERSION`, `APP_COMMIT`, "unknown" when unset); the account service had asked for "dev" as the version default
**Revisit when:** a deployment path appears that cannot set the two variables, or the services move to a shared health router

`Health(status, version, commit)` with `Health.from_env()` is the
`/healthz` body. An unset or blank `APP_VERSION` or `APP_COMMIT` is
`"unknown"`. Core ships the model, not a route: every service keeps its
own `/healthz`.

**Reason:** a probe must never fail over a label, so a missing value
gets a default, not a `ConfigError`. "unknown" says what is true: nothing
was set. "dev" would claim a development build on a production pod whose
ConfigMap lost the variable. The routes stay in the services because
they already differ (account's pings its database) and core does not
depend on FastAPI outside `web.py`.

**Rejected alternative:** `"dev"` as the version default (account's
proposal). It reads as information while it is the absence of it.

**Rejected alternative:** a shared health router in `lasteverlm_core.web`.
Every service would have to give up or wrap its own readiness check for
two fields.
