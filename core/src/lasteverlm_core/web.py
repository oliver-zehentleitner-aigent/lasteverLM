"""FastAPI glue for the admin-only endpoints of ingest and rag.

Needs FastAPI, which every service has and core does not depend on, so
this module is not re-exported from the package root:
`from lasteverlm_core.web import admin_only`.

The JWT carries no admin claim; whether a caller is an admin is read
from `users.is_admin` on every request, so revoking it takes effect at
once. The service supplies the lookup because only it knows its pool.
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

AdminLookup = Callable[[Request, UUID], bool | Awaitable[bool]]

ADMIN_ONLY = "admin only"


def admin_only(
    current_user: Callable[..., Any], lookup: AdminLookup
) -> Callable[..., Awaitable[UUID]]:
    """A dependency that resolves the caller with the service's own
    `current_user` dependency (401 stays its job) and answers 403 unless
    `lookup(request, user_id)` says admin. A sync lookup (a psycopg pool
    call) runs in a worker thread; an async one is awaited.
    """

    is_async = inspect.iscoroutinefunction(lookup)

    async def dependency(request: Request, user_id: Annotated[UUID, Depends(current_user)]) -> UUID:
        if is_async:
            result = lookup(request, user_id)
        else:
            result = await run_in_threadpool(lookup, request, user_id)
        # a plain lambda around an async call hands back its coroutine
        admin = await result if inspect.isawaitable(result) else result
        if not admin:
            raise HTTPException(status_code=403, detail=ADMIN_ONLY)
        return user_id

    return dependency
