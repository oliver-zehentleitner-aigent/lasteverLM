"""Outgoing mail over SMTP. The configuration lives in the ``settings`` table (key
``smtp``) and is edited by an admin through the API; the environment only seeds it.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from typing import Any, Protocol


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

    @classmethod
    def from_setting(cls, value: dict[str, Any]) -> SmtpConfig:
        return cls(
            host=str(value.get("host", "")),
            port=int(value.get("port", 587)),
            username=str(value.get("username", "")),
            password=str(value.get("password", "")),
            from_address=str(value.get("from_address", "")),
            starttls=bool(value.get("starttls", True)),
        )

    def to_setting(self) -> dict[str, Any]:
        return asdict(self)

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


def magic_link_mail(link: str, ttl_minutes: int) -> tuple[str, str]:
    subject = "Your lasteverLM sign-in link"
    body = (
        "Open this link to sign in to lasteverLM:\n\n"
        f"{link}\n\n"
        f"It works once and expires in {ttl_minutes} minutes. "
        "If you did not request it, ignore this mail.\n"
    )
    return subject, body
