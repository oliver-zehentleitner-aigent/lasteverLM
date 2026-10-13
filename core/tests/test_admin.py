"""`is_admin`, `admin_role`, `has_credit` and their async twins against the
fake connections, and the `admin_only` / `admin_read` dependencies inside a
real FastAPI app."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from lasteverlm_core import (
    HAS_CREDIT_SQL,
    IS_ADMIN_SQL,
    ROLE_SQL,
    Role,
    aadmin_role,
    admin_role,
    ahas_credit,
    ais_admin,
    has_credit,
    is_admin,
)
from lasteverlm_core.web import admin_only, admin_read

from .conftest import FakeAsyncConnection, FakeConnection
from .test_ratelimit import run_asgi

USER = uuid4()


def test_sync_checks_read_tuple_and_dict_rows() -> None:
    for rows in ([(True,), (False,)], [{"is_admin": True}, {"has_credit": False}]):
        conn = FakeConnection(rows=list(rows))
        assert is_admin(conn, USER) is True
        assert has_credit(conn, USER) is False
        assert conn.executed == [
            (IS_ADMIN_SQL, {"user_id": USER}),
            (HAS_CREDIT_SQL, {"user_id": USER}),
        ]


async def test_async_checks() -> None:
    conn = FakeAsyncConnection(rows=[(False,), (True,)])
    assert await ais_admin(conn, USER) is False
    assert await ahas_credit(conn, USER) is True
    assert [sql for sql, _ in conn.executed] == [IS_ADMIN_SQL, HAS_CREDIT_SQL]


# --- admin_only -----------------------------------------------------------------

ADMINS = {USER}


def current_user(x_user: Annotated[str | None, Header()] = None) -> UUID:
    """Stands in for a service's bearer-token dependency."""
    if x_user is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return UUID(x_user)


def sync_lookup(request: Request, user_id: UUID) -> bool:
    return user_id in ADMINS


async def async_lookup(request: Request, user_id: UUID) -> bool:
    return user_id in ADMINS


def app_with(lookup: Any) -> FastAPI:
    app = FastAPI()
    admin = Depends(admin_only(current_user, lookup))

    # a default, not Annotated: this module's annotations are strings and
    # FastAPI cannot resolve a local alias from them
    @app.get("/x")
    async def endpoint(user_id: UUID = admin) -> dict[str, str]:
        return {"admin": str(user_id)}

    return app


def headers(user: UUID) -> list[tuple[bytes, bytes]]:
    return [(b"x-user", str(user).encode())]


async def test_admin_only_with_sync_async_and_lambda_lookups() -> None:
    for lookup in (sync_lookup, async_lookup, lambda r, u: async_lookup(r, u)):
        app = app_with(lookup)
        status, body = await run_asgi(app, headers(USER))
        assert status == 200 and str(USER).encode() in body
        status, body = await run_asgi(app, headers(uuid4()))
        assert status == 403 and b"admin only" in body
        status, _ = await run_asgi(app, [])
        assert status == 401  # the service's own dependency still decides who


def test_credit_check_ignores_the_admin_flag() -> None:
    assert "is_admin" not in HAS_CREDIT_SQL and "users" not in HAS_CREDIT_SQL


# --- roles and admin_read ---------------------------------------------------------


async def test_admin_role_reads_tuple_and_dict_rows() -> None:
    for row in [("viewer",), {"role": "viewer"}]:
        conn = FakeConnection([row])
        assert admin_role(conn, USER) == "viewer"
        assert conn.executed == [(ROLE_SQL, {"user_id": USER})]
    assert await aadmin_role(FakeAsyncConnection([("admin",)]), USER) == "admin"
    with pytest.raises(ValueError, match="unknown role 'root'"):
        admin_role(FakeConnection([("root",)]), USER)


ROLES_BY_USER: dict[UUID, Role] = {}


def sync_role(request: Request, user_id: UUID) -> Role:
    return ROLES_BY_USER.get(user_id, "user")


async def async_role(request: Request, user_id: UUID) -> Role:
    return ROLES_BY_USER.get(user_id, "user")


async def test_admin_read_admits_viewers_and_admins_admin_only_admins() -> None:
    viewer, admin, user = uuid4(), uuid4(), uuid4()
    ROLES_BY_USER.update({viewer: "viewer", admin: "admin", user: "user"})
    for lookup in (sync_role, async_role):
        app = FastAPI()
        read = Depends(admin_read(current_user, lookup))
        write = Depends(admin_only(current_user, lambda r, u: sync_role(r, u) == "admin"))

        @app.get("/stats")
        async def stats(user_id: UUID = read) -> dict[str, str]:
            return {"reader": str(user_id)}

        @app.post("/stats")
        async def change(user_id: UUID = write) -> dict[str, str]:
            return {"writer": str(user_id)}

        for who, can_read in ((viewer, True), (admin, True), (user, False), (uuid4(), False)):
            status, body = await run_asgi(app, headers(who), path="/stats")
            assert (status, b"admin only" in body) == ((200, False) if can_read else (403, True))
        assert (await run_asgi(app, [], path="/stats"))[0] == 401
        # reading is not writing: a viewer is refused where admin_only gates
        assert (await run_asgi(app, headers(viewer), path="/stats", method="POST"))[0] == 403
        assert (await run_asgi(app, headers(admin), path="/stats", method="POST"))[0] == 200
