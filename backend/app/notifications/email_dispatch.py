"""Asynchronous email delivery — the reusable "send one email, off the request
path" capability.

WHY THIS EXISTS
===============
``EmailService`` (email_service.py) is a synchronous SMTP client: it opens a
connection, authenticates against the Brevo relay and blocks until the message
has been handed over — up to ``SMTP_TIMEOUT`` seconds. That is fine inside a
Celery worker, which is where the only pre-existing caller (the daily report
reminder) runs it. It is NOT fine inside an HTTP request: a slow or unreachable
relay would stall the user's own action, even when the work that action performed
has already been committed.

This module is the missing middle. It turns "send this message" into a JSON
payload, hands that payload to a Celery task, and returns immediately. The
transport, its configuration and its credentials are UNCHANGED — every send still
goes through ``EmailService`` and the same Brevo SMTP settings
(``SMTP_HOST=smtp-relay.brevo.com``, ``SMTP_FROM=noreply@coreops.cdccmms.com``,
``EMAIL_ENABLED``). Nothing here reads a credential, names a provider or builds a
second transport.

WHAT IT DELIBERATELY DOES NOT DO
================================
It knows nothing about leave, reports, employees or templates. Callers hand it a
subject and an already-rendered body, exactly as they already hand them to
``EmailService``. Business rules and HTML rendering stay in ``app.reminders.*``
and future feature modules, per the layering ``app/notifications/__init__.py``
describes. This file is transport plumbing and nothing else.

ENQUEUING NEVER RAISES ON A DELIVERY CONDITION
==============================================
``enqueue_email`` returns an :class:`EnqueueResult` and swallows broker failures.
The FastAPI app deliberately does not depend on Celery being up — ``core/
celery_app.py`` and ``deploy/DEPLOYMENT.md`` both state the API keeps serving
with the worker stopped — so a Redis outage must not turn into a 500 on an action
that has already succeeded. The caller gets ``queued=False`` and a machine-
readable ``reason``, and decides what to do about it.

It never silently falls back to a blocking send: doing so would reintroduce the
very stall this module exists to avoid, at exactly the moment the infrastructure
is least healthy. A caller that genuinely wants to block asks for that explicitly
via :func:`send_email_now`.

A MALFORMED PAYLOAD *DOES* RAISE
================================
``EmailPayloadError`` is raised for a caller bug — an empty subject, an empty
body, an attachment larger than the broker should ever carry. Those are
deterministic and would fail identically on every retry, so they surface at the
call site rather than being buried in a worker log.

RECIPIENTS ARE NORMALISED ONCE, HERE
====================================
Blank entries are dropped and duplicates are removed CASE-INSENSITIVELY, because
addresses arrive from CITEXT columns (``employees.work_email``, ``users.email``)
where ``A@x.com`` and ``a@x.com`` are the same mailbox. Two code paths that each
resolve the same person must not produce two emails.
"""
from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass

from app.notifications.config import EmailSettings, get_email_settings
from app.notifications.email_service import Attachment, EmailService

logger = logging.getLogger("coreops.notifications.email")

# Payload schema version. Carried in every message so a worker running older code
# during a rolling deploy can recognise — and refuse — a shape it does not know,
# instead of silently mis-sending it.
PAYLOAD_VERSION = 1

# Upper bound on the total decoded attachment bytes a single QUEUED message may
# carry. The broker is Redis, holding the payload in memory until a worker picks
# it up, so a large attachment is a memory cost multiplied by every queued
# message. Anything bigger belongs in a synchronous worker-side send (the daily
# report reminder's CSV route) or behind a download link.
MAX_ASYNC_ATTACHMENT_BYTES = 5 * 1024 * 1024

# Guard rails on the message itself, so a bug upstream cannot enqueue something
# no relay would accept anyway.
MAX_SUBJECT_LENGTH = 500
MAX_RECIPIENTS = 50

# Reasons an enqueue can decline. Machine-readable so callers can branch without
# string-matching prose.
REASON_NO_RECIPIENTS = "no_recipients"
REASON_EMAIL_DISABLED = "email_disabled"
REASON_NOT_CONFIGURED = "not_configured"
REASON_BROKER_UNAVAILABLE = "broker_unavailable"


class EmailPayloadError(ValueError):
    """The message itself is malformed — a caller bug, not a delivery failure."""


@dataclass(frozen=True)
class EnqueueResult:
    """What :func:`enqueue_email` did.

    ``queued`` is the only field a caller must check. ``reason`` is set exactly
    when ``queued`` is False and names one of the ``REASON_*`` constants above.
    """

    queued: bool
    task_id: str | None = None
    reason: str | None = None
    recipients: tuple[str, ...] = ()

    @property
    def skipped(self) -> bool:
        """True when nothing was queued for a NON-error reason (no recipients,
        or email switched off) — as opposed to the broker being unreachable."""
        return not self.queued and self.reason in {
            REASON_NO_RECIPIENTS,
            REASON_EMAIL_DISABLED,
        }


# ---------- recipients ------------------------------------------------------

def normalise_recipients(to: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Trim, drop blanks, and de-duplicate case-insensitively, preserving order.

    The first spelling of an address wins, so the display form the caller chose
    is what appears in the header.
    """
    if to is None:
        return []
    raw = [to] if isinstance(to, str) else list(to)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        address = (item or "").strip()
        if not address:
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(address)
    return out


# ---------- payload ---------------------------------------------------------

def build_payload(
    *,
    to: str | list[str] | tuple[str, ...] | None,
    subject: str,
    html_body: str = "",
    text_body: str | None = None,
    attachments: list[Attachment] | None = None,
    text_only: bool = False,
) -> dict:
    """A JSON-safe dict describing one message.

    Celery's serializer is JSON, so attachment bytes are base64-encoded here and
    decoded again by :func:`payload_to_attachments` in the worker. Raises
    :class:`EmailPayloadError` for anything that would fail identically on every
    retry.

    ``text_only=True`` declares a single-part ``text/plain`` message: ``html_body``
    is then irrelevant and ``text_body`` becomes the required one. The default is
    False, which keeps the original rule — an HTML body is mandatory — for every
    caller that has not asked for anything different.

    The flag rides in the payload WITHOUT a ``PAYLOAD_VERSION`` bump, because it
    is purely additive: a worker running older code reads the payload it already
    understands and sends the multipart message it always did. Bumping the
    version would instead make that worker refuse the message outright, turning a
    cosmetic difference into a dropped email during a rolling deploy.
    """
    recipients = normalise_recipients(to)
    if len(recipients) > MAX_RECIPIENTS:
        raise EmailPayloadError(
            f"Too many recipients: {len(recipients)} (max {MAX_RECIPIENTS}). "
            "Send one message per recipient instead of a single large To: header."
        )

    subject = (subject or "").strip()
    if not subject:
        raise EmailPayloadError("subject must not be empty.")
    if len(subject) > MAX_SUBJECT_LENGTH:
        raise EmailPayloadError(
            f"subject is {len(subject)} characters (max {MAX_SUBJECT_LENGTH})."
        )
    if text_only:
        if not (text_body or "").strip():
            raise EmailPayloadError(
                "text_body must not be empty for a text_only message."
            )
    elif not (html_body or "").strip():
        raise EmailPayloadError("html_body must not be empty.")

    encoded: list[dict] = []
    total_bytes = 0
    for attachment in attachments or []:
        total_bytes += len(attachment.content)
        if total_bytes > MAX_ASYNC_ATTACHMENT_BYTES:
            raise EmailPayloadError(
                f"Attachments total more than {MAX_ASYNC_ATTACHMENT_BYTES} bytes; "
                "too large to queue. Send synchronously from a worker, or link to "
                "the file instead of attaching it."
            )
        encoded.append(
            {
                "filename": attachment.filename,
                "content_b64": base64.b64encode(attachment.content).decode("ascii"),
                "maintype": attachment.maintype,
                "subtype": attachment.subtype,
            }
        )

    return {
        "version": PAYLOAD_VERSION,
        "to": recipients,
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
        "text_only": bool(text_only),
        "attachments": encoded,
    }


def payload_to_attachments(payload: dict) -> list[Attachment]:
    """Rebuild the :class:`Attachment` list from a queued payload."""
    out: list[Attachment] = []
    for item in payload.get("attachments") or []:
        try:
            content = base64.b64decode(item["content_b64"], validate=True)
        except (KeyError, binascii.Error, ValueError) as exc:
            raise EmailPayloadError(
                f"Attachment {item.get('filename', '<unnamed>')!r} is not valid "
                "base64."
            ) from exc
        out.append(
            Attachment(
                filename=item["filename"],
                content=content,
                maintype=item.get("maintype", "application"),
                subtype=item.get("subtype", "octet-stream"),
            )
        )
    return out


# ---------- delivery (worker side) ------------------------------------------

def deliver_payload(payload: dict, *, email_service: EmailService | None = None) -> bool:
    """Hand one queued payload to SMTP. Runs inside the Celery worker.

    Returns what ``EmailService.send`` returns: True when the message reached the
    relay, False when the send was skipped (``EMAIL_ENABLED=false``, or no
    recipients survived normalisation). Propagates ``EmailSendError`` so the task
    wrapping this can retry a transport failure.
    """
    version = payload.get("version")
    if version != PAYLOAD_VERSION:
        raise EmailPayloadError(
            f"Unsupported email payload version {version!r} "
            f"(this worker understands {PAYLOAD_VERSION}). "
            "A newer API enqueued a shape this worker cannot read — deploy the "
            "worker before the API, or drain the queue."
        )

    service = email_service or EmailService()
    return service.send(
        to=list(payload.get("to") or []),
        subject=payload["subject"],
        # `.get` rather than `[...]`: a text_only payload legitimately carries no
        # HTML at all, and an older payload predating the flag carries no
        # `text_only` key. Both must read as "the shape this worker already knows".
        html_body=payload.get("html_body") or "",
        text_body=payload.get("text_body"),
        attachments=payload_to_attachments(payload) or None,
        text_only=bool(payload.get("text_only", False)),
    )


# ---------- enqueue (caller side) -------------------------------------------

def enqueue_email(
    *,
    to: str | list[str] | tuple[str, ...] | None,
    subject: str,
    html_body: str = "",
    text_body: str | None = None,
    attachments: list[Attachment] | None = None,
    settings: EmailSettings | None = None,
    text_only: bool = False,
) -> EnqueueResult:
    """Queue one email for the Celery worker to deliver. Returns immediately.

    ``text_only=True`` queues a single-part ``text/plain`` message and needs no
    ``html_body`` at all — see :func:`build_payload`.

    Never raises for a delivery condition — no recipients, email switched off, an
    unconfigured or unreachable broker all come back as ``queued=False`` with a
    ``reason``. Raises :class:`EmailPayloadError` only for a malformed message,
    which is a caller bug.

    Celery is imported lazily, inside this function, so merely importing this
    module keeps the API process free of Celery exactly as it is today.
    """
    recipients = normalise_recipients(to)
    if not recipients:
        logger.warning("email.enqueue_skipped reason=%s subject=%r",
                       REASON_NO_RECIPIENTS, subject)
        return EnqueueResult(queued=False, reason=REASON_NO_RECIPIENTS)

    # Checked here as well as inside EmailService: a disabled or half-configured
    # environment should cost nothing at all, not a round trip through the broker
    # and a worker wake-up that ends in a skip.
    email_settings = settings or get_email_settings()
    if not email_settings.EMAIL_ENABLED:
        logger.info(
            "email.enqueue_skipped reason=%s to=%s subject=%r "
            "(set EMAIL_ENABLED=true to send)",
            REASON_EMAIL_DISABLED, recipients, subject,
        )
        return EnqueueResult(
            queued=False,
            reason=REASON_EMAIL_DISABLED,
            recipients=tuple(recipients),
        )
    if not email_settings.is_configured:
        logger.error(
            "email.enqueue_skipped reason=%s to=%s subject=%r "
            "(SMTP_HOST / SMTP_FROM missing)",
            REASON_NOT_CONFIGURED, recipients, subject,
        )
        return EnqueueResult(
            queued=False,
            reason=REASON_NOT_CONFIGURED,
            recipients=tuple(recipients),
        )

    # Built BEFORE the broker call so a malformed message fails at the call site
    # rather than in a worker the caller cannot see.
    payload = build_payload(
        to=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachments=attachments,
        text_only=text_only,
    )

    try:
        from app.tasks.email_tasks import send_email as send_email_task

        async_result = send_email_task.delay(payload)
    except Exception as exc:  # noqa: BLE001 - the broker must never break a caller
        logger.error(
            "email.enqueue_failed reason=%s to=%s subject=%r error=%s",
            REASON_BROKER_UNAVAILABLE, recipients, subject, exc,
        )
        return EnqueueResult(
            queued=False,
            reason=REASON_BROKER_UNAVAILABLE,
            recipients=tuple(recipients),
        )

    task_id = getattr(async_result, "id", None)
    logger.info(
        "email.enqueued task_id=%s to=%s subject=%r", task_id, recipients, subject
    )
    return EnqueueResult(queued=True, task_id=task_id, recipients=tuple(recipients))


def send_email_now(
    *,
    to: str | list[str] | tuple[str, ...] | None,
    subject: str,
    html_body: str = "",
    text_body: str | None = None,
    attachments: list[Attachment] | None = None,
    email_service: EmailService | None = None,
    text_only: bool = False,
) -> bool:
    """Deliver one email SYNCHRONOUSLY, through the same validation and
    normalisation the queued path uses.

    For callers that are already off the request path (a Celery worker, a
    management script, a debug endpoint) and want the result now. A request
    handler should use :func:`enqueue_email` instead — this blocks for as long as
    the relay takes.
    """
    payload = build_payload(
        to=to,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachments=attachments,
        text_only=text_only,
    )
    if not payload["to"]:
        logger.warning("email.skip reason=%s subject=%r", REASON_NO_RECIPIENTS, subject)
        return False
    return deliver_payload(payload, email_service=email_service)
