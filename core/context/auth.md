# Authentication

## One resolver for both token schemes, JWT first, demo second

**Id:** 1a54c35a-d06b-46c7-8de3-b9d0575d33f7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design and family coordination, 2026-10-12 (reconciling the three services' local mirrors)
**Revisit when:** a third scheme (password, OAuth) is added, or DEMO_TOKEN is removed from the contract

`current_user(authorization, auth)` is the only place a bearer token
becomes a user. When `AUTH_JWT_SECRET` is set the token is tried as a
session JWT (HS256, issuer `lasteverlm`, `sub` = user id, no audience
claim); when that fails and `DEMO_TOKEN` is set the token is compared to
it in constant time and resolves to the fixed demo user. Both schemes may
be configured at once, and the result says which one matched
(`Principal.scheme`).

**Reason:** before core existed, each service mirrored the resolver and
the three mirrors disagreed. One made the demo token exclusive (a set
`DEMO_TOKEN` rejected every JWT), one required an audience claim the
account service never issues, so real logins would have failed at that
service. A development deployment needs to log in by mail and run a
recorded demo with the token at the same time, and production only has
to leave `DEMO_TOKEN` unset. Carrying the scheme in the result lets an
admin endpoint refuse the demo token without a second decode.

**Rejected alternative:** exactly one scheme per deployment, chosen by
which variable is set. Simpler to reason about, rejected because it makes
the demo token and mail login mutually exclusive in the one environment
where both are wanted.

**Rejected alternative:** an `aud` claim on session tokens. Nothing in
the family consumes tokens for more than one audience; the claim would
have been a constant that two services must keep equal for no benefit.
Issuer verification stays, because a token from another HS256 system
with a leaked secret should still fail.

## A session secret shorter than 32 bytes is refused

**Id:** dd3ccf4e-52f4-4601-ba95-d06e1e7eed9d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security audit of core, 2026-10-14, confirmed by the coordinator; RFC 7518 section 3.2 (an HS256 key at least as long as the hash output)
**Revisit when:** the token algorithm changes from HS256

`AuthSettings` raises `ConfigError` when `jwt_secret` is shorter than
`MIN_JWT_SECRET_BYTES` (32). The check is in the dataclass itself, not
only in `from_env`, because the account service, which issues the tokens,
builds its settings without `from_env`.

**Reason:** with HS256, the secret is everything that protects a session.
A short secret can be brute-forced offline from any token, and the
result is a valid session for any user. The deployment's generated secret
is 64 characters long, so the check only stops a hand-set short one, at
startup instead of in an incident.

**Rejected alternative:** only in `from_env`. That would miss the one
service that signs.
