# Admin settings

## The allowlist from the environment is a seed, applied once

**Id:** 41b86a10-a780-48a8-9f75-e70992bf4d06
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination and family architecture v1, 2026-10-12

`AUTH_ALLOWED_DOMAINS` is copied into the `settings` table at the first
start that finds the key missing, and ignored afterwards. The admin panel
(`PUT /admin/settings/domains`) is the only place that changes it later;
a redeploy with a different environment value does nothing.

Narrowed on 2026-10-13: this entry covered `SMTP_*` as well until the
mail configuration moved to the environment only (the entry below); the
seed-once rule now applies to the allowlist alone.

**Reason:** the family wants the allowlist editable at run time by an
admin without a redeploy, and a value that can be edited in two places
needs a rule for which one wins. "Environment seeds, database owns" is
the rule that never silently reverts what an admin changed. The test
`test_startup_seeds_settings_only_once` pins it.

**Rejected alternative:** environment always wins when set — rejected
because an admin's change would vanish at the next rollout with no
visible cause.

Refined after the first live deployment (2026-10-12): an *empty*
persisted allowlist is re-seeded from a non-empty `AUTH_ALLOWED_DOMAINS`
at startup. The first deploy ran with an empty seed, persisted `[]`, and
from then on no environment value could ever let anyone in — a lockout
by design, not a decision anyone made. An empty list is read as "never
configured"; an admin who wants to deny everyone sets `ADMIN_EMAILS`
empty as well, which the startup log warns about.

## The SMTP password is stored in plain text in the settings table

**Id:** c132f8c9-0be7-4b06-a237-95c956521825
**Type:** workaround
**Status:** superseded
**Superseded by:** 3a1628c3-2a18-4df6-a184-b5b03b26a74f
**Evidence:** confirmed
**Source:** implementation, 2026-10-12
**Revisit when:** the family settles how services get an encryption key, or the database is shared with anything outside the cluster

The admin-entered SMTP password lives as a plain string inside the
`jsonb` value of `settings.smtp`. The API never returns it (the read
shape has no password field, an update without one keeps the stored
value), but anyone with read access to the database can see it.

**Reason:** encrypting it at rest needs a key that every replica of this
service shares and that is not in the same database — a second secret
to provision, rotate and hand to the infra repository. That key handling
is a family-wide question not settled at the time of writing, and the
database is a managed instance reachable only from the cluster. The
limitation is named in `SECURITY.md` so nobody mistakes it for an
oversight.

**Rejected alternative:** Fernet encryption with a key from
`AUTH_JWT_SECRET` — rejected because it reuses the session-token secret
for a second purpose, so a leak of either exposes both.

## The mail configuration comes from the environment only, shown read-only in the admin panel

**Id:** 3a1628c3-2a18-4df6-a184-b5b03b26a74f
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-13
**See:** admin-settings.md#the-smtp-password-is-stored-in-plain-text-in-the-settings-table — c132f8c9-0be7-4b06-a237-95c956521825 — as of 2026-10-13
**Revisit when:** a monitoring that mails without the database is built (it must read the same `SMTP_*`), or the family introduces a secrets backend other than Kubernetes Secrets

`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_FROM_ADDRESS` and `SMTP_STARTTLS` are read once at start into
`Settings.smtp`; the mailer uses that object. `GET /admin/settings/smtp`
returns host, port, username, from address and starttls so an admin sees
what is in effect, never the password; `PUT /admin/settings/smtp` no
longer exists. The `settings` table holds no SMTP row; a row left from
the time the admin panel stored it is deleted at every start.
`AUTH_ALLOWED_DOMAINS` and `ADMIN_EMAILS` are untouched by this.

**Reason:** two. Every other secret of the family lives in a Kubernetes
Secret; the admin-entered SMTP password in `jsonb` was the one exception
and needed a workaround entry of its own to explain why it was tolerable.
And a later monitoring that mails when the database is unreachable needs
the whole mail configuration without the database — a configuration
stored *in* the database cannot serve that case by definition. Reading
it from the environment removes the exception and keeps the door open
for the monitoring, which is not built now.

**Rejected alternative:** password in the Secret, the rest (host, port,
user, from, starttls) still editable in the database — rejected because
the monitoring mail needs all of it, not only the password, and a
configuration split over two places needs a rule for which wins (the
same problem the seed-once rule solved for the allowlist).

**Consequence:** changing the mail server means changing the Secret and
restarting the pods; the panel cannot do it. The variable names stay as
they were; the Secret is `lasteverlm-smtp`, renamed by infra on the same
day because nothing is seeded any more.
