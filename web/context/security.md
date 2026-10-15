# Security

## Content-Security-Policy enforced, behind a build switch, after a clean browser run

**Id:** 6743c3f5-5a44-451b-874d-16ff9bb8e2e6
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** instruction after the night audit, 2026-10-14 (a build-time or env switch, default off; the hash derived at build; a headless browser run in Docker by infra decides when it flips); infra's report-mode run, 2026-10-14 (`make web-csp-check` in `infra/`): 0 violations over every page, report, quiz, table, mind map, infographic, the share page and the theme toggle; the modes and the generator were this directory's call
**Revisit when:** a page needs a source the policy does not list, an audio output shows a violation (audio was not in the run: the demo account had none; `media-src` allows any `https:` origin, which the presigned URLs are), or the storage host is fixed enough to narrow `CSP_MEDIA_SRC` to it

The full policy (`default-src 'self'`, the inline theme script by its
sha256, `style-src 'self' 'unsafe-inline'`, images and audio from
`'self'`, `data:`/`blob:` and the object storage, frames from `'self'`
and the object storage, `connect-src 'self'`
plus `API_BASE_URL`'s origin, `object-src 'none'`, `base-uri 'none'`,
`frame-ancestors 'none'`) is written into the image at build by
`scripts/csp.mjs`. The build arg `CSP` picks `enforce` (the default
since the clean run), `report` (the full policy as
`Content-Security-Policy-Report-Only` beside the enforced
`frame-ancestors`, the mode the check runs in) or `off` (only
`frame-ancestors`, the earlier state).

**Re-checked 2026-10-15** (two of the revisit conditions fired: the
source viewer needed frames, so `frame-src` was added with it on
2026-10-14, and the production build narrows `CSP_MEDIA_SRC` to the
object storage origin in infra's `docker.yml`). The decision stands.

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

A `preview_url` is only ever rendered inline (as an `<img>`) for an
image; for a PDF or text it is the presigned original and for a web page
the page's own address, both only for the open link in a new tab. Since
2026-10-14 the source viewer shows a PDF's presigned original in an
iframe and a web page as the stored snapshot in a sandboxed iframe (no
scripts, no same origin, no referrer); the page's own address is still
only a link, never loaded by the viewer. Found
by infra's walk on v0.10.2, 2026-10-14: thumbnails for every entry with
a preview fetched each web page a user once added from the viewer's
browser (third-party requests, an `http:` one tripping `img-src`) and
showed presigned PDFs as broken images. `ImageName` checks the kind
itself, so no call site can bring it back.

**Rejected alternative:** a thumbnail for any kind with an `onError`
fallback to the plain name. Rejected because the request still goes out
before the fallback, which is the leak.

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

## The sign-in code field exchanges the mail's code; no field takes a Bearer token

**Id:** 7d1f4a78-1112-4be0-92c3-5544e7d95883
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer walkthrough, 2026-10-14: the code pasted from the sign-in mail led to a 401 on every request

The login page's second form takes the code the sign-in mail prints
under the link and exchanges it at `/api/account/auth/callback`, as the
link does; the JWT that comes back is stored. Before, the form stored
whatever was pasted as the Bearer token, a path meant for the
development token `demo`, so the mail's code, the one thing a user has
to paste, could not work. The code's format is checked before it is
sent. A raw Bearer token has no field anymore: nothing in the repository
signs in through the form (the CSP walk sets the token in local storage,
the smoke test sends it as a header), and docs/development.md says how
to set one by hand.

**Rejected alternative:** keep the Bearer field and add a second one for
the code. Rejected because two fields that look alike, one of which
works only for developers, would leave the user to pick the one that
works.
