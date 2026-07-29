"""Run-completion notifications (email/Slack) - PRD fast-follow.

Mirrors the JobRunner/Storage pattern elsewhere in app/core: a Protocol,
a zero-infra no-op default, and concrete backends selected by a single
Settings flag. Notification failures must never fail the run itself -
callers (app/recon/engine.py) wrap notify() in a broad try/except.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, subject: str, message: str) -> None: ...


class NoopNotifier:
    """Default: logs instead of sending anything - zero infra required,
    same rationale as InProcessJobRunner/LocalFsStorage being the dev
    defaults for their respective abstractions."""

    def notify(self, subject: str, message: str) -> None:
        logger.info("Notification (backend=none, not sent): %s - %s", subject, message)


class EmailNotifier:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str, recipients: list[str]) -> None:
        self._host, self._port, self._user, self._password = host, port, user, password
        self._sender, self._recipients = sender, recipients

    def notify(self, subject: str, message: str) -> None:
        if not self._recipients:
            logger.warning("EmailNotifier has no recipients configured (NOTIFY_EMAIL_TO) - skipping send")
            return
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        msg.set_content(message)

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def notify(self, subject: str, message: str) -> None:
        response = httpx.post(self._webhook_url, json={"text": f"*{subject}*\n{message}"}, timeout=10)
        response.raise_for_status()


class MultiNotifier:
    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    def notify(self, subject: str, message: str) -> None:
        for n in self._notifiers:
            n.notify(subject, message)


_notifier_instance: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier_instance
    if _notifier_instance is not None:
        return _notifier_instance

    settings = get_settings()
    backend = settings.notify_backend.lower()

    email = EmailNotifier(
        settings.smtp_host, settings.smtp_port, settings.smtp_user,
        settings.smtp_password, settings.smtp_from, settings.notify_email_to,
    )
    slack = SlackNotifier(settings.slack_webhook_url)

    if backend == "email":
        _notifier_instance = email
    elif backend == "slack":
        _notifier_instance = slack
    elif backend == "both":
        _notifier_instance = MultiNotifier([email, slack])
    else:
        _notifier_instance = NoopNotifier()
    return _notifier_instance
