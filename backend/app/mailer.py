"""Sending email over SMTP (standard library only).

Settings (environment):
  SMTP_HOST         server name; email is off when this is empty
  SMTP_PORT         default 587 (465 when SMTP_SECURITY=ssl)
  SMTP_SECURITY     starttls (default), ssl or none
  SMTP_USER, SMTP_PASSWORD   login, if the server needs one
  SMTP_FROM         sender, e.g. "ClearPay4U <payroll@clearpay4u.com>"
  APP_URL           public address of the web app, used in links (e.g. https://app.clearpay4u.com)

With Docker Compose, mail goes to Mailpit: open http://localhost:8025 to see every email sent.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid

log = logging.getLogger("clearpay4u.mail")


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None


class MailError(Exception):
    pass


class SmtpMailer:
    def __init__(self, env: dict | None = None):
        e = os.environ if env is None else env
        self.host = e.get("SMTP_HOST", "").strip()
        self.security = e.get("SMTP_SECURITY", "starttls").strip().lower()
        self.port = int(e.get("SMTP_PORT") or (465 if self.security == "ssl" else 587))
        self.user = e.get("SMTP_USER", "")
        self.password = e.get("SMTP_PASSWORD", "")
        self.sender = e.get("SMTP_FROM", "ClearPay4U <no-reply@clearpay4u.local>")
        self.timeout = float(e.get("SMTP_TIMEOUT", "10"))

    @property
    def enabled(self) -> bool:
        return bool(self.host)

    def send(self, email: Email) -> None:
        if not self.enabled:
            raise MailError("Email is not set up (SMTP_HOST is empty)")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, email.to, email.subject
        msg["Message-ID"] = make_msgid(domain="clearpay4u")
        msg.set_content(email.text)
        if email.html:
            msg.add_alternative(email.html, subtype="html")
        try:
            if self.security == "ssl":
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout,
                                          context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with server:
                if self.security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if self.user:
                    server.login(self.user, self.password)
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            log.warning("Email to %s failed: %s", email.to, exc)
            raise MailError(f"Could not send the email ({exc.__class__.__name__})") from exc
        log.info("Email sent to %s: %s", email.to, email.subject)


@dataclass
class Outbox:
    """Keeps emails in memory instead of sending them (tests)."""

    sent: list[Email] = field(default_factory=list)
    enabled: bool = True
    fail: bool = False

    def send(self, email: Email) -> None:
        if self.fail:
            raise MailError("Could not send the email (test)")
        self.sent.append(email)


def app_url() -> str:
    return os.environ.get("APP_URL", "").rstrip("/")
