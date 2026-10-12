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
