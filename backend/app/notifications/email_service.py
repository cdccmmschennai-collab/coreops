"""EmailService — reusable SMTP transport.

Single responsibility: deliver a rendered message over SMTP. It knows nothing
about reminders, reports, PMs, or HTML generation — callers hand it a subject and
body and it sends. This keeps it reusable for any future notification type.

Design notes
------------
* Configuration is injected (``EmailSettings``) so the service is trivially
  testable and can be pointed at a fake SMTP in tests.
* ``EMAIL_ENABLED=false`` makes ``send`` a logged no-op (returns False) so a
  half-configured environment never raises.
* Failures raise ``EmailSendError`` so orchestration layers can decide whether to
  continue (the daily-reminder dispatcher isolates failures per PM).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.notifications.config import EmailSettings, get_email_settings

logger = logging.getLogger("coreops.notifications.email")


class EmailSendError(RuntimeError):
    """Raised when an email could not be delivered to the SMTP server."""


class EmailService:
    """Thin, reusable SMTP client. Construct once and reuse across sends."""

    def __init__(self, settings: EmailSettings | None = None) -> None:
        self._settings = settings or get_email_settings()

    def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> bool:
        """Send one message. Returns True if handed to SMTP, False if skipped.

        Raises ``EmailSendError`` on any SMTP/transport failure.
        """
        recipients = [to] if isinstance(to, str) else list(to)
        recipients = [r for r in recipients if r]
        if not recipients:
            logger.warning("email.skip reason=no_recipients subject=%r", subject)
            return False

        settings = self._settings
        if not settings.EMAIL_ENABLED:
            logger.info(
                "email.skip reason=disabled to=%s subject=%r "
                "(set EMAIL_ENABLED=true to send)",
                recipients,
                subject,
            )
            return False
        if not settings.is_configured:
            raise EmailSendError(
                "SMTP is not configured (SMTP_HOST / SMTP_FROM missing)."
            )

        message = self._build_message(recipients, subject, html_body, text_body)

        try:
            self._deliver(message, recipients)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error(
                "email.error to=%s subject=%r error=%s",
                recipients,
                subject,
                exc,
            )
            raise EmailSendError(str(exc)) from exc

        logger.info("email.sent to=%s subject=%r", recipients, subject)
        return True

    # -- internals -----------------------------------------------------------

    def _build_message(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str | None,
    ) -> EmailMessage:
        settings = self._settings
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.from_address))
        message["To"] = ", ".join(recipients)
        # A plain-text part is always set so non-HTML clients render something.
        message.set_content(text_body or _html_to_text_fallback(html_body))
        message.add_alternative(html_body, subtype="html")
        return message

    def _deliver(self, message: EmailMessage, recipients: list[str]) -> None:
        settings = self._settings
        if settings.SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT,
                context=context,
            ) as client:
                self._authenticate(client)
                client.send_message(message, to_addrs=recipients)
            return

        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
        ) as client:
            if settings.SMTP_USE_TLS:
                client.starttls(context=ssl.create_default_context())
            self._authenticate(client)
            client.send_message(message, to_addrs=recipients)

    def _authenticate(self, client: smtplib.SMTP) -> None:
        settings = self._settings
        if settings.SMTP_USERNAME:
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)


def _html_to_text_fallback(html_body: str) -> str:
    """Very small HTML->text degradation for the plain-text alternative.

    Not a full renderer — reminder templates supply their own text body, so this
    only guards ad-hoc callers that pass HTML only.
    """
    import re

    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|h[1-6]|li)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
