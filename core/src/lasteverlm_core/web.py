"""FastAPI glue for the admin endpoints of the services.

Needs FastAPI, which every service has and core does not depend on, so
this module is not re-exported from the package root:
`from lasteverlm_core.web import admin_only, admin_read`.

`admin_only` gates what changes something (admins), `admin_read` what
only reads (viewers and admins). The JWT carries no role claim; the role
is read from `users` on every request, so a change takes effect at once.
The service supplies the lookup because only it knows its pool.
"""

# No `from __future__ import annotations`: FastAPI reads the dependency's
# annotations at runtime, and `current_user` is a closure variable that a
# string annotation could not resolve.
import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .models import Role

AdminLookup = Callable[[Request, UUID], bool | Awaitable[bool]]
RoleLookup = Callable[[Request, UUID], Role | Awaitable[Role]]

ADMIN_ONLY = "admin only"
# Who may read the admin area; writing stays with "admin" (`admin_only`).
READ_ROLES: frozenset[Role] = frozenset({"viewer", "admin"})


def _gate(
    current_user: Callable[..., Any],
    lookup: Callable[[Request, UUID], Any],
    admits: Callable[[Any], bool],
) -> Callable[..., Awaitable[UUID]]:
    """The dependency both gates share: resolve the caller with the service's
    own `current_user` (401 stays its job), ask `lookup` (a sync one runs in
    a worker thread, an async one is awaited) and answer 403 unless `admits`."""

    is_async = inspect.iscoroutinefunction(lookup)

    async def dependency(request: Request, user_id: Annotated[UUID, Depends(current_user)]) -> UUID:
        if is_async:
            result = lookup(request, user_id)
        else:
            result = await run_in_threadpool(lookup, request, user_id)
        # a plain lambda around an async call hands back its coroutine
        value = await result if inspect.isawaitable(result) else result
        if not admits(value):
            raise HTTPException(status_code=403, detail=ADMIN_ONLY)
        return user_id

    return dependency


def admin_only(
    current_user: Callable[..., Any], lookup: AdminLookup
) -> Callable[..., Awaitable[UUID]]:
    """Admins only: the dependency for every endpoint that changes something.
    403 unless `lookup(request, user_id)` says admin."""
    return _gate(current_user, lookup, bool)


def admin_read(
    current_user: Callable[..., Any], role_lookup: RoleLookup
) -> Callable[..., Awaitable[UUID]]:
    """Viewers and admins: the dependency for admin endpoints that only read.
    `role_lookup(request, user_id)` returns the caller's `Role`
    (`admin_role` / `aadmin_role`); 403 for "user"."""
    return _gate(current_user, role_lookup, lambda role: role in READ_ROLES)
