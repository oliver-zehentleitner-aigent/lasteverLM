# Notes pane

## Notes live in the browser, not on the server

**Id:** 0a016a24-126a-4637-94e7-b292950dd0f5
**Type:** decision
**Status:** superseded
**Superseded by:** f81a9fe1-d433-4e32-b143-ed29542a8722
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12; API contract v1 in the parent repository

The first skeleton had a notes pane: a free-text area per notebook stored
in `localStorage`. Nothing was sent to a service; the notes did not follow
the user to another browser.

**Superseded** on 2026-10-12 by the two-column layout without a notes
pane (`frontend.md`): saved answers become a Report output, so the pane
has no job left, and the browser-local storage is removed with it.

**Reason:** the v1 contract has no notes endpoint, and none of the three
services owns notes. The pane is part of the three-pane shape the MVP
requires, so it has to exist; a browser-local text is the smallest
version that makes it useful without widening any service's contract.

**Rejected alternative:** a notes endpoint on ingest or rag. Rejected for
v1 because it would add a table and an endpoint to a service whose owner
has not asked for it, and the contract change would have to go through
the parent first. Candidate for later, together with whatever the UI
concept decides notes are for.
