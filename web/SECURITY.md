# Security

## Reporting

Report vulnerabilities privately through GitHub's
[security advisories](https://github.com/oliver-zehentleitner/lasteverLM/security/advisories/new)
for the lasteverLM repository. Do not open a public issue. You will get a response
within a few days.

## Scope and model

- This is a static single-page app. It holds no secrets: the only
  build-time input is the API base URL. Everything sensitive lives in the
  backend services of the repository. Secrets never enter the repository.
- The session token (a JWT issued by the account service, or a development
  access token) is stored in `localStorage` and sent as a bearer header to
  the family's API prefixes only. Signing out removes it. A 401 from any
  endpoint discards it.
- Admin pages are shown only to users the API marks `is_admin`; the API
  enforces that independently with 403.
- Generated documents come from a language model and are treated as
  untrusted content: Markdown is rendered with `marked` and sanitized with
  DOMPurify before it is inserted; every other kind is rendered through
  React, which escapes text. Shared documents on `/s/<token>` get the same
  treatment.
- The app records page views for the aggregated visitor log; it sends the
  path, nothing else. IP handling is the account service's concern.
- Dependencies: React, `marked`, DOMPurify and markmap at runtime; Vite,
  TypeScript, oxlint and vitest for development. `npm audit` runs in CI at
  level high for runtime dependencies.
