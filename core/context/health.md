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

## Dependencies in /healthz are reported, they never fail liveness

**Id:** 8361fe81-5e63-424c-a479-b7df46fb0c2c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the coordinator's spec for the live architecture diagram, 2026-10-14 (status stays "ok" while the process is up; checks bounded and cached for 15 s)
**Revisit when:** the chart gets a readiness probe that should take a service out of rotation on a dependency outage, or the diagram needs more than up/down

`Health.dependencies` reports `"ok"` or `"down"` for each dependency
the service uses. `status` stays `"ok"` as long as the process answers.
A failed check is reported and logged as a warning. It never raises and
never turns `/healthz` into an error. `DependencyProbe` runs the checks
concurrently, gives each 2 s and serves the states from a 15 s cache.
While a service runs no probe, the key is left out of the body.

**Reason:** `/healthz` is also the Kubernetes liveness probe. If it
failed on a database or inference outage, every pod would restart in a
loop and the API would disappear entirely. Users would lose the clear
answers it can still give, and the admin view would lose the place
where it shows the outage. The 2 s bound and the cache keep a slow
dependency from holding the probe or from being called on every poll.

**Rejected alternative:** a non-200 or `status: "degraded"` when a
dependency is down. The liveness probe would read it as a dead process.

**Rejected alternative:** an empty `dependencies` in every body. Every
service test that pins the body would have changed before any service
reports anything. Leaving the key out keeps the change additive until
each service wires its probe.
