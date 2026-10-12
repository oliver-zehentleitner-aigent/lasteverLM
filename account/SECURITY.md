# Security

## Reporting

Please report vulnerabilities privately through GitHub's
"Report a vulnerability" on the lasteverLM repository, not as a public issue.
You will get an answer within a few days.

## What this service protects

- **Login** is passwordless. A sign-in link carries a random 256-bit token; only its SHA-256 hash is stored, it is single use and expires after 15 minutes. Whether an address is allowed to log in is never revealed by the API.
- **Session tokens** are HS256 JWTs signed with `AUTH_JWT_SECRET`; use at least 32 random bytes and rotate by redeploying all services with the new value.
- **Voucher codes** are stored hashed; the plain code is shown once to the admin who created it.
- **Admin routes** require `is_admin`; the shared demo identity can never be admin.
- **Visitor log** stores no IP address and no full user agent, see the Privacy section of the README.

## Known limitations

- The SMTP password is stored in plain text in the `settings` table of the shared database. Anyone with database access can read it. Encrypting it at rest with a key from the environment is planned once the key handling for all services is settled, see `context/admin-settings.md`.
- There is no rate limit on `POST /auth/request-link` in the service itself; the ingress is expected to provide one. Until it does, an attacker can make the service send many mails to an allowed address.
