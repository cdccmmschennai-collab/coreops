"""The one generic email task.

Thin trigger, same convention as ``periodic_tasks.py``: the task body contains no
SMTP, no templating and no SQL. It hands the payload straight to
``notifications.email_dispatch.deliver_payload``, which is where the transport
lives.

WHY THIS TASK RETRIES AND THE SCHEDULED ONES DO NOT
===================================================
The daily report reminder runs on a fixed daily schedule: a failed run is
naturally retried tomorrow, and re-sending it an hour later would be noise. An
event-driven email has no such second chance — nothing will fire it again — so a
transient relay failure has to be retried here or the message is simply lost.

Only ``EmailSendError`` is retried. It is the one error ``EmailService`` raises
for a transport problem, and the overwhelmingly common cases (relay unreachable,
connection reset, greylisting, a timeout) all clear on their own. A malformed
payload raises ``EmailPayloadError`` instead, which is deliberately NOT in
``autoretry_for``: it would fail identically on all four attempts, so it fails
once, loudly.

A permanently-refused recipient does come back as ``EmailSendError`` and will be
retried a few times before it gives up. That is a deliberate trade: four wasted
attempts on a dead address costs nothing, while not retrying a live one loses a
real notification.

Backoff is exponential with jitter, capped at ten minutes, over at most three
retries — so a message survives a relay blip of roughly twenty minutes and then
stops rather than queueing forever.
"""
from __future__ import annotations

import logging

from app.core.celery_app import EMAIL_SEND_TASK, celery_app
from app.notifications.email_dispatch import deliver_payload
from app.notifications.email_service import EmailSendError

logger = logging.getLogger("coreops.notifications.email")

EMAIL_MAX_RETRIES = 3
EMAIL_RETRY_BACKOFF_MAX_SECONDS = 600


@celery_app.task(
    name=EMAIL_SEND_TASK,
    bind=True,
    autoretry_for=(EmailSendError,),
    retry_backoff=True,
    retry_backoff_max=EMAIL_RETRY_BACKOFF_MAX_SECONDS,
    retry_jitter=True,
    max_retries=EMAIL_MAX_RETRIES,
)
def send_email(self, payload: dict) -> dict:
    """Deliver one queued email. Returns a small, JSON-safe summary.

    ``sent=False`` with no exception means the send was deliberately skipped -
    ``EMAIL_ENABLED=false``, or no recipients survived normalisation - which is
    a success, not a failure, and must not be retried.
    """
    recipients = list(payload.get("to") or [])
    subject = payload.get("subject")
    attempt = self.request.retries

    try:
        sent = deliver_payload(payload)
    except EmailSendError as exc:
        # Logged on every attempt so the journal shows the whole retry story, not
        # only the final give-up. Re-raised for autoretry_for to pick up.
        logger.warning(
            "email.task_failed to=%s subject=%r attempt=%d/%d error=%s",
            recipients, subject, attempt + 1, EMAIL_MAX_RETRIES + 1, exc,
        )
        raise

    logger.info(
        "email.task_done to=%s subject=%r sent=%s attempt=%d",
        recipients, subject, sent, attempt + 1,
    )
    return {
        "sent": sent,
        "recipients": len(recipients),
        "attempts": attempt + 1,
    }
