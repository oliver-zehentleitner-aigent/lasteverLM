# Preferences

## The verification level is stored as the user's intent, not as a judge setting

**Id:** 24018a2f-0a93-4ae0-8346-306bcfebb480
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15; level names and meaning defined by rag
**Revisit when:** the old web client is gone (then `judge_default` in `PUT` is dropped), or a level needs a value the four names cannot express

`users.preferences.verification_level` is `basic`, `standard`, `thorough` or
`bulletproof`, default `basic`: how much checking matters to the user and how much
it may cost. rag defines what each level does (whether a judge runs, at which
strength); the web preselects the output form from it, rag's agent chat reads it.
It replaces `judge_default` (off|low|medium|high, added the same week without an
entry of its own), which named the mechanism. Migration 0011 maps stored values
(off to basic, low to standard, medium to thorough, high to bulletproof) and keeps
`judge_default` in the row; a row without the new key reads mapped; the service
writes only the new key, so the old one disappears at the user's next preferences
write. `PUT /me/preferences` still takes `judge_default` for one release, mapped,
the new field winning when both are sent; it is no longer returned.

**Reason:** a user decides how much checking is worth to them, not which judge
model runs. Storing that intent lets rag change what a level does, for example
add a second check or a different model, without migrating anyone's setting.
`basic` as the default keeps the cost of a new user's first actions as before,
when no judge ran unless chosen.

**Rejected alternatives:** keeping `judge_default` and only renaming it in the web
— the stored value would still name the mechanism and tie every later change of
the checks to a data migration; removing `judge_default` from the rows in the
migration — a pod of the previous release reads it during the rollout and would
fall back to off; rejecting `judge_default` in `PUT` at once — an open browser
tab with the old web would fail to save its settings.
