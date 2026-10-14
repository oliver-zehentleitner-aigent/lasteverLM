# Security

## Reporting

Please report vulnerabilities privately through GitHub's
"Report a vulnerability" on the lasteverLM repository, not as a public issue.
You will get an answer within a few days.

## What this service protects

- **Login** is passwordless. A sign-in link carries a random 256-bit token (also usable as a pasted code); only its SHA-256 hash is stored, it is single use and expires after 15 minutes. An address outside the allowlist is told so (403 `not_allowed`) by the maintainer's decision: the allowlist is a handful of partner domains, not a secret, and a link only ever reaches the address itself (`context/auth.md`).
- **Session tokens** are HS256 JWTs signed with `AUTH_JWT_SECRET`, valid for `JWT_TTL_DAYS` (1) day. Sign-out is client-side: the web drops the token, the service keeps no session list and cannot revoke a single token before it expires; a magic link is cheap to request again, so the window is kept short. Immediate revocation of every session means rotating `AUTH_JWT_SECRET` in all services. Use at least 32 random bytes for the secret.
- **Voucher codes** are stored as a SHA-256 hash (the redeem looks them up by hash) and, since 0.10, AES-GCM-encrypted under `VOUCHER_KEY`, a key that lives only in the environment, so an admin can show or mail a code again. A database leak alone yields neither spendable codes nor the key; the database plus the key does. Codes created before 0.10 exist only as hashes and stay unrecoverable.
- **SMTP password** exists only in the environment (Kubernetes Secret `lasteverlm-smtp`), never in the database and never in an API response.
- **Admin routes**: every write requires the `admin` role, every read `viewer` or `admin`; the role lives on the user row and is changed only by an admin, who cannot demote the last admin; the shared demo identity is refused before the lookup and can never hold a role above `user`.
- **Visitor log** stores no IP address and no full user agent, see the Privacy section of the README.
- **Security logs** (`access_log`, `login_attempts`, blocks and bans) keep the raw client address for 30 days, admins only; a malformed `X-Forwarded-For` is stored as `0.0.0.0`, never passed on.
- **Kubernetes** is read with the pod's own ServiceAccount, two `GET`s on this namespace only, 5-second timeouts; the token never appears in logs or responses.

## Known limitations

- Rate limiting is core's middleware (120 requests per minute per IP, then blocks and bans) plus a per-address quota of `LINK_QUOTA_PER_HOUR` (5) sign-in links per hour; a throttled request writes no `login_attempts` row. Refused addresses are still logged within the IP budget (254-byte rows, 30-day retention).
