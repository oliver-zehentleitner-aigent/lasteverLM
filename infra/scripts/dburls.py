#!/usr/bin/env python3
"""Derives the connection strings the cluster needs from the admin URL.

Reads DATABASE_ADMIN_URL (the managed instance's admin role, any database)
and APP_DB_PASSWORD, prints shell assignments, every URL with
sslmode=verify-full against the CA the pods mount at PG_CA_PATH:

  DATABASE_URL            application role on the `lasteverlm` database
  DATABASE_ADMIN_APP_URL  admin role on the `lasteverlm` database (migrations)
  DATABASE_ADMIN_URL      admin role on its own database (bootstrap), normalized

Values are shell-quoted; nothing is printed on error but the reason.
"""

import os
import shlex
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit

APP_USER = os.environ.get("APP_DB_USER", "lasteverlm")
APP_DB = os.environ.get("APP_DB_NAME", "lasteverlm")
PG_CA_PATH = os.environ.get("PG_CA_PATH", "/etc/lasteverlm/pg-ca.crt")


def with_credentials(url: str, user: str, password: str, dbname: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    query = f"sslmode=verify-full&sslrootcert={quote(PG_CA_PATH, safe='/')}"
    return urlunsplit((parts.scheme, netloc, f"/{dbname}", query, ""))


def main() -> int:
    admin = os.environ.get("DATABASE_ADMIN_URL")
    password = os.environ.get("APP_DB_PASSWORD")
    if not admin or not password:
        print("DATABASE_ADMIN_URL and APP_DB_PASSWORD are required", file=sys.stderr)
        return 1
    parts = urlsplit(admin)
    if not (parts.username and parts.password and parts.hostname):
        print("DATABASE_ADMIN_URL must carry user, password and host", file=sys.stderr)
        return 1
    # urlsplit keeps userinfo percent-encoded; decode before re-encoding.
    admin_user, admin_pw = unquote(parts.username), unquote(parts.password)
    admin_db = parts.path.lstrip("/") or "defaultdb"
    print(f"DATABASE_URL={shlex.quote(with_credentials(admin, APP_USER, password, APP_DB))}")
    print(
        f"DATABASE_ADMIN_APP_URL={shlex.quote(with_credentials(admin, admin_user, admin_pw, APP_DB))}"
    )
    print(
        f"DATABASE_ADMIN_URL={shlex.quote(with_credentials(admin, admin_user, admin_pw, admin_db))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
