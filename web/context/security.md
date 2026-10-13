# Security

## Content-Security-Policy limited to frame-ancestors for now

**Id:** 40aee3ef-7710-41cf-b1c7-f21dd4109882
**Type:** decision
**Status:** active
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
