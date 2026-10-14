"""What a viewer (the read-only admin role) sees of e-mail addresses: core's mask, applied
at the server, so the full address never leaves account for that role. Admins see
everything (context/privacy.md, "A viewer gets e-mail addresses masked by the server")."""

from __future__ import annotations

from typing import Any, cast

from lasteverlm_core import Role, mask_email, masks_emails
from pydantic import BaseModel

from .repository import UserRecord

# Per response model: the fields that carry an address; a list field masks every element.
# Smtp's from_address and username are the service's own mailbox and stay.
ADDRESS_FIELDS: dict[str, tuple[str, ...]] = {
    "AdminUserView": ("email",),
    "AdminLogin": ("email",),
    "AdminLoginAttempt": ("email",),
    "Allowlist": ("allowed_addresses", "viewer_addresses"),
    "AdminVoucher": ("created_by", "redeemed_by", "sent_to"),
    "UserUsage": ("email",),
    "StarterNotebook": ("set_by",),
}


def _masked(value: Any) -> Any:
    if isinstance(value, str):
        return mask_email(value)
    if isinstance(value, list):
        return [mask_email(v) if isinstance(v, str) else v for v in value]
    return value  # None stays None


def mask[T: BaseModel](model: T) -> T:
    """A copy of ``model`` with every address field masked; nested models are walked."""
    update: dict[str, Any] = {
        name: _masked(getattr(model, name)) for name in ADDRESS_FIELDS.get(type(model).__name__, ())
    }
    for name, value in model:
        if isinstance(value, BaseModel):
            update[name] = mask(value)
        elif isinstance(value, list) and value and isinstance(value[0], BaseModel):
            update[name] = [mask(v) for v in value]
    return model.model_copy(update=update)


def masks(reader: UserRecord) -> bool:
    return masks_emails(cast(Role, reader.role))


def for_reader[T: BaseModel](reader: UserRecord, value: T) -> T:
    return mask(value) if masks(reader) else value


def for_reader_list[T: BaseModel](reader: UserRecord, values: list[T]) -> list[T]:
    return [mask(v) for v in values] if masks(reader) else values


def for_reader_keys[T: BaseModel](reader: UserRecord, value: T, field: str = "rows") -> T:
    """Finance rows grouped by user: the key is the address (or the user id once the user
    is gone, which stays); masked for a viewer."""
    if not masks(reader):
        return value
    rows = [
        r.model_copy(update={"key": mask_email(r.key)}) if "@" in r.key else r
        for r in getattr(value, field)
    ]
    return value.model_copy(update={field: rows})
