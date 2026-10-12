"""Development entrypoint: the full API on in-memory storage, no PostgreSQL, no SMTP.

``make run-dev`` starts it. Sign-in links are printed to the console instead of
mailed; ``admin@example.org`` is allowed and becomes admin, the demo user exists
with the demo token ``demo``. Nothing here is used in a deployed service.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

from lasteverlm_core import DEMO_USER_EMAIL, DEMO_USER_ID

from .config import Settings
from .mail import SmtpConfig
from .main import create_app
from .repository import UserRecord
from .repository_memory import MemoryRepository
from .service import SETTING_SMTP

DEV_SETTINGS = Settings(
    database_url="memory://",
    auth_jwt_secret="dev-only-secret-never-use-in-production-0000",
    public_base_url="http://localhost:8000",
    demo_token="demo",
    admin_emails=frozenset({"admin@example.org"}),
    allowed_domains_seed=("example.org",),
)


class ConsoleMailer:
    """Prints the mail instead of sending it, so the link can be copied from the terminal."""

    async def send(self, config: SmtpConfig, to: str, subject: str, body: str) -> None:
        print(f"\n--- mail to {to}: {subject}\n{body}--- end mail\n", file=sys.stderr, flush=True)


def _seeded_repository() -> MemoryRepository:
    repo = MemoryRepository()
    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, DEMO_USER_EMAIL, False, datetime.now(UTC), None
    )
    repo.settings[SETTING_SMTP] = SmtpConfig(
        "console", 25, "", "", "noreply@localhost", False
    ).to_setting()
    return repo


logging.basicConfig(level="INFO")
app = create_app(settings=DEV_SETTINGS, repository=_seeded_repository(), mailer=ConsoleMailer())
