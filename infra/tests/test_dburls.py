import os
import shlex
import subprocess
import sys
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "dburls.py")


def run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base = {"PATH": os.environ.get("PATH", "")}
    return subprocess.run(
        [sys.executable, SCRIPT], env={**base, **env}, capture_output=True, text=True, check=False
    )


def parsed(stdout: str) -> dict[str, str]:
    out = {}
    for line in stdout.splitlines():
        name, _, value = line.partition("=")
        out[name] = shlex.split(value)[0]
    return out


class DbUrlsTest(unittest.TestCase):
    def test_three_urls_with_verify_full_and_the_right_roles(self) -> None:
        r = run(
            {
                "DATABASE_ADMIN_URL": "postgresql://vultradmin:p%40ss@db.example:16751/defaultdb?sslmode=require",
                "APP_DB_PASSWORD": "app pw/+",
            }
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        urls = parsed(r.stdout)
        self.assertEqual(
            set(urls), {"DATABASE_URL", "DATABASE_ADMIN_APP_URL", "DATABASE_ADMIN_URL"}
        )
        for name, user, password, db in [
            ("DATABASE_URL", "lasteverlm", "app pw/+", "lasteverlm"),
            ("DATABASE_ADMIN_APP_URL", "vultradmin", "p@ss", "lasteverlm"),
            ("DATABASE_ADMIN_URL", "vultradmin", "p@ss", "defaultdb"),
        ]:
            u = urlsplit(urls[name])
            self.assertEqual((unquote(u.username), unquote(u.password)), (user, password), name)
            self.assertEqual((u.hostname, u.port, u.path), ("db.example", 16751, f"/{db}"), name)
            query = parse_qs(u.query)
            self.assertEqual(query["sslmode"], ["verify-full"], name)
            self.assertEqual(query["sslrootcert"], ["/etc/lasteverlm/pg-ca.crt"], name)

    def test_missing_input_fails_without_printing_a_url(self) -> None:
        r = run({"DATABASE_ADMIN_URL": "postgresql://u:secret@h:1/db"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertNotIn("secret", r.stderr)

    def test_admin_url_without_password_is_refused(self) -> None:
        r = run({"DATABASE_ADMIN_URL": "postgresql://u@h:1/db", "APP_DB_PASSWORD": "x"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
