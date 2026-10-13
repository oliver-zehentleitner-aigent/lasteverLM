# Security

## Reporting

Please report vulnerabilities privately through GitHub's
"Report a vulnerability" on the lasteverLM repository, not as a public issue.
You will get an answer within a few days.

## What this service protects

- **Login** is passwordless. A sign-in link carries a random 256-bit token (also usable as a pasted code); only its SHA-256 hash is stored, it is single use and expires after 15 minutes. An address outside the allowlist is told so (403 `not_allowed`) by the maintainer's decision: the allowlist is a handful of partner domains, not a secret, and a link only ever reaches the address itself (`context/auth.md`).
- **Session tokens** are HS256 JWTs signed with `AUTH_JWT_SECRET`; use at least 32 random bytes and rotate by redeploying all services with the new value.
- **Voucher codes** are stored hashed; the plain code is shown once to the admin who created it.
- **SMTP password** exists only in the environment (Kubernetes Secret `lasteverlm-smtp`), never in the database and never in an API response.
- **Admin routes** require `is_admin`; the shared demo identity can never be admin.
- **Visitor log** stores no IP address and no full user agent, see the Privacy section of the README.
- **Security logs** (`access_log`, `login_attempts`, blocks and bans) keep the raw client address for 30 days, admins only; a malformed `X-Forwarded-For` is stored as `0.0.0.0`, never passed on.
- **Kubernetes** is read with the pod's own ServiceAccount, two `GET`s on this namespace only, 5-second timeouts; the token never appears in logs or responses.

## Known limitations

- Rate limiting is core's middleware (120 requests per minute per address, then blocks and bans); within that budget a caller can make the service send sign-in mails to an allowed address and fill `login_attempts` rows (254-byte address, 30-day retention). No per-address mail quota exists yet.
