"""Outgoing mail over SMTP. The configuration comes from the environment (``SMTP_*``),
is read once at start and is never stored; the admin panel shows it read-only.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


class MailError(RuntimeError):
    """The mail could not be handed to the SMTP server."""


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    starttls: bool

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_address)


class Mailer(Protocol):
    async def send(self, config: SmtpConfig, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    """Blocking smtplib in a worker thread; one connection per message is fine at this volume."""

    timeout_seconds: float = 20.0

    async def send(self, config: SmtpConfig, to: str, subject: str, body: str) -> None:
        if not config.configured:
            raise MailError("SMTP is not configured")
        message = EmailMessage()
        message["From"] = config.from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            await asyncio.to_thread(self._deliver, config, message)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(str(exc)) from exc

    def _deliver(self, config: SmtpConfig, message: EmailMessage) -> None:
        with smtplib.SMTP(config.host, config.port, timeout=self.timeout_seconds) as smtp:
            if config.starttls:
                smtp.starttls()
            if config.username:
                smtp.login(config.username, config.password)
            smtp.send_message(message)


def magic_link_mail(link: str, token: str, ttl_minutes: int) -> tuple[str, str]:
    """The sign-in mail: the link first, the same token as a code to paste second, because
    the sign-in page offers both ways in."""
    subject = "Your lasteverLM sign-in link"
    body = (
        "Open this link to sign in to lasteverLM:\n\n"
        f"{link}\n\n"
        "Or paste this code on the sign-in page:\n\n"
        f"{token}\n\n"
        f"Link and code are the same sign-in: it works once and expires in {ttl_minutes} "
        "minutes. If you did not request it, ignore this mail.\n"
    )
    return subject, body
