"""What a read-only viewer of the admin area may see of a person.

A viewer sees e-mail addresses masked: the domain in full, the local
part reduced to its first and last character with three stars between
them, always three, so the length does not show. An admin sees them in
full. The services decide per request with `masks_emails(role)` and mask
with `mask_email`, or do both with `email_for`.
"""

from __future__ import annotations

from .models import Role

MASK = "***"


def mask_email(address: str) -> str:
    """`jane.doe@example.com` -> `j***e@example.com`.

    A local part of one character becomes `*`, of two its first character
    and `*`. Input without a usable `@` (no local part or no domain) is
    masked whole, as `***`. The last `@` splits, as in a quoted local part
    that contains one."""
    local, at, domain = address.rpartition("@")
    if not at or not local or not domain:
        return MASK
    if len(local) == 1:
        return f"*@{domain}"
    if len(local) == 2:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}{MASK}{local[-1]}@{domain}"


def masks_emails(role: Role) -> bool:
    """Whether this role sees e-mail addresses masked: a viewer does."""
    return role == "viewer"


def email_for(role: Role, address: str) -> str:
    """The address as `role` may see it."""
    return mask_email(address) if masks_emails(role) else address
