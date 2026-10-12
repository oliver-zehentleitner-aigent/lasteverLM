# Admin settings

## Environment values for SMTP and domains are seeds, applied once

**Id:** 41b86a10-a780-48a8-9f75-e70992bf4d06
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination and family architecture v1, 2026-10-12

`AUTH_ALLOWED_DOMAINS` and `SMTP_*` are copied into the `settings`
table at the first start that finds the key missing, and ignored
afterwards. The admin panel (`PUT /admin/settings/...`) is the only
place that changes them later; a redeploy with a different environment
value does nothing.

**Reason:** the family wants these two values editable at run time by an
admin without a redeploy, and a value that can be edited in two places
needs a rule for which one wins. "Environment seeds, database owns" is
the rule that never silently reverts what an admin changed. The test
`test_startup_seeds_settings_only_once` pins it.

**Rejected alternative:** environment always wins when set — rejected
because an admin's change would vanish at the next rollout with no
visible cause.

## The SMTP password is stored in plain text in the settings table

**Id:** c132f8c9-0be7-4b06-a237-95c956521825
**Type:** workaround
**Status:** active
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
