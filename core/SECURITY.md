# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
private vulnerability reporting on this repository ("Report a
vulnerability" under the Security tab). You will get an acknowledgement
and a plan within a few days.

## What this library is responsible for

- Session tokens are HS256 JWTs with the issuer `lasteverlm`; `verify_jwt` requires `sub`, `exp` and `iss` and accepts no other algorithm. The demo token is compared in constant time and resolves only to the fixed demo user; production deployments leave `DEMO_TOKEN` unset.
- `current_user` is the one place a bearer token becomes a user; services call it and never decode tokens themselves.
- The rate-limit middleware trusts `X-Forwarded-For` only because the ingress sets it and pods are not reachable otherwise; a service exposed directly passes `trust_forwarded=False`. A value that is not an IP address is recorded as `0.0.0.0`, never interpolated.
- Raw client IPs are stored only in `access_log`, `ip_blocks` and `ip_bans`, for this purpose, and `purge` removes them after the retention period (an active ban stays until an admin lifts it).
- All SQL uses bound parameters; no value from a request is formatted into a statement.
- Secrets come from the environment only. Nothing in this directory is a secret.

## Supported versions

Only the current `main` branch is supported.
