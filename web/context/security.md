# Security

## Content-Security-Policy behind a build switch, off until a browser run is clean

**Id:** 6743c3f5-5a44-451b-874d-16ff9bb8e2e6
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family lead's instruction after the night audit, 2026-10-14 (a build-time or env switch, default off; the hash derived at build; a headless browser run in Docker by infra decides when it flips); the modes and the generator were this directory's call
**Revisit when:** the report-mode run against the live API shows no violations (then the default becomes `enforce`), or a page needs a source the policy does not list

The full policy (`default-src 'self'`, the inline theme script by its
sha256, `style-src 'self' 'unsafe-inline'`, images and audio from
`'self'`, `data:`/`blob:` and the object storage, `connect-src 'self'`
plus `API_BASE_URL`'s origin, `object-src 'none'`, `base-uri 'none'`,
`frame-ancestors 'none'`) is written into the image at build by
`scripts/csp.mjs`. The build arg `CSP` picks `off` (only
`frame-ancestors`, the previous state, still the default), `report`
(the full policy as `Content-Security-Policy-Report-Only` beside the
enforced `frame-ancestors`) or `enforce`.

**Reason:** the reasons the earlier entry gave for not shipping a policy
unverified still hold: a wrong one blanks a page silently. A report
mode makes the browser list every violation while blocking nothing, so
the policy can be judged on the deployed image before it is enforced.
Deriving the hash from the built `index.html` means the theme script can
change without anyone recomputing it by hand, which is the usual way a
hashed policy breaks. `'unsafe-inline'` stays for styles because markmap
writes a `<style>` element and inline style attributes; scripts, the
part that matters against injected markup, get no `'unsafe-inline'`.

**Rejected alternative:** a hand-written hash in `security-headers.conf`.
Rejected because it drifts from the script the moment the script
changes.

**Rejected alternative:** a nonce. Rejected because nginx serves a
static `index.html`; a nonce would need a per-response rewrite of the
page for one constant script, where a hash of that script does the
same.

**Rejected alternative:** a runtime environment variable instead of a
build arg. Rejected because the hash belongs to the built file anyway,
so the policy and the page it protects are fixed together in one image.

## Content-Security-Policy limited to frame-ancestors for now

**Id:** 40aee3ef-7710-41cf-b1c7-f21dd4109882
**Type:** decision
**Status:** superseded
**Superseded by:** 6743c3f5-5a44-451b-874d-16ff9bb8e2e6
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-13, after the click-through of the live domain
**Revisit when:** a browser run of the app against the image is possible (the build VM has no runnable Chromium), or the audio player's URL origin is settled

The web image sends `nosniff`, `Referrer-Policy: no-referrer` and a
no-framing policy on every response. The Content-Security-Policy carries
only `frame-ancestors 'none'`; there is no `script-src`, `style-src`,
`connect-src` or `media-src` yet.

**Reason:** a full policy is the stronger defence against script from
model output, but it can only be judged in a browser: the lazy-loaded
mind map injects its own styles, `API_BASE_URL` may point to another
origin, and the audio URL's origin is not fixed. A wrong policy blanks
the app or a document silently, and nothing here could have shown it
before the deployment. Model output is already sanitized (see
outputs.md), so the gap is defence in depth, not the only line.

**Rejected alternative:** a full policy (`default-src 'self'`,
`style-src 'self' 'unsafe-inline'`, `img-src 'self' data:`) shipped
unverified. Rejected for the risk of breaking the live app on a guess.

**Rejected alternative:** `Referrer-Policy: strict-origin-when-cross-origin`
(the browser default). Rejected because `no-referrer` costs nothing
here and keeps a share link's token out of every outgoing request.
