# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
private vulnerability reporting on this repository ("Report a
vulnerability" under the Security tab). You will get an acknowledgement
and a plan within a few days.

## What this service trusts and does not trust

- Every request carries a bearer token; the service resolves it to a user and scopes every query to that user. There is no anonymous access except `/healthz`.
- Uploaded files are parsed with pure-Python libraries; file names are reduced to a safe character set before they become object keys; uploads are capped by `MAX_UPLOAD_BYTES`.
- URL sources are not fetched in v1. When the url loader is added, it must refuse private, loopback and link-local addresses and cap the response size, because the service runs inside the cluster.
- Secrets come from the environment only. Nothing in this repository is a secret, and `.env` is ignored by Git.
- Error messages returned to users never contain internal exception text; those go to the log.

## Supported versions

Only the current `main` branch is supported.
