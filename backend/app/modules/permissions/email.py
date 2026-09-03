"""The permission email: "a request is waiting for you" (Phase 4C).

WHAT THIS SENDS, AND WHEN
==========================
One message, for one event, fired from one named call site in `service.py` and
nowhere else: an employee submits a permission request ->
:func:`send_submission_email`, called from `create_permission_request` after the
request is committed and after the existing in-app notification. Approval,
rejection and cancellation stay in-app only, exactly as Leave's decision events
do for everything except the two decision emails it also sends - Phase 4C's scope
is the submission email and the four duration options, nothing more.

SAME LETTER, SAME INFRASTRUCTURE AS LEAVE
============================================
Plain text plus the thinnest possible HTML alternative, same reasoning as
`leave/email.py`'s module docstring: a permission request is correspondence
between two colleagues, not a designed notification. `build_link` is imported
from `leave.email` rather than re-implemented - it is a small pure function
("an absolute URL for an in-app path, given the configured base URL") with
nothing leave-specific in it, and re-implementing the trailing-slash handling a
second time is exactly the kind of drift reuse is meant to prevent. The actual
transport (`enqueue_email`) is the SAME shared sender every CoreOps email goes
through - nothing here builds a second one.

WHO IT GOES TO
===============
The first candidate in `permissions.recipients.resolve_permission_recipients`
with a `work_email`: the routed project's current Head, else the requester's
reporting PM. That is the exact same chain, walked in the same order, that the
in-app notification (`service._notify_routed_approver`) uses - the two channels
differ only in the reachability test each applies (a `work_email` vs a
`user_id`), so they can never disagree about WHO the recipient is, only about
whether that person is reachable on this particular channel.

`Employee.work_email` is the only address consulted. `User.email` is a login
identity and is deliberately never used as a fallback, for the same reason
`leave/email.py` never uses it.

FAILURE IS NEVER THE CALLER'S PROBLEM
=======================================
`send_submission_email` returns None and never raises. It runs after the request
it describes has already been committed and the in-app notification already
delivered, so nothing it does may endanger either: an unresolvable recipient, a
malformed payload, an unreachable broker or a bug in the renderer all end as a
log line, exactly as `leave/email.py::send_submission_email` behaves.
"""
from __future__ import annotations

import html as _html
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.employees.models import Employee
from app.modules.leave.email import build_link
from app.modules.permissions.models import PermissionRequest, duration_label
from app.modules.permissions.recipients import (
    PermissionRecipient,
    permission_request_path,
    resolve_permission_recipients,
)
from app.notifications.email_dispatch import enqueue_email

logger = logging.getLogger("coreops.permissions.email")

# Matches the leave email's format, so every CoreOps email reads the same way:
# "28 Aug 2026".
_DATE_FMT = "%d %b %Y"


@dataclass(frozen=True)
class RenderedPermissionEmail:
    """One ready-to-send permission email: a text/plain body and its minimal
    HTML twin. Same shape as `leave.email.RenderedLeaveEmail`, for the same
    reason - see that module's docstring."""

    subject: str
    text_body: str
    html_body: str


# ---------- pure rendering --------------------------------------------------

def render_submission_email(
    *,
    recipient_name: str,
    employee_name: str,
    permission_date: date,
    duration_label: str,
    reason: str | None,
    request_id: str,
    link: str | None,
) -> RenderedPermissionEmail:
    """Turn one submitted permission request into a subject and a plain-text
    body. Pure: no database, no SMTP - everything it needs is an argument, the
    same discipline `leave.email.render_submission_email` follows."""
    product = settings.PRODUCT_NAME
    clean_reason = (reason or "").strip()

    details = [
        ("Permission Date", permission_date.strftime(_DATE_FMT)),
        ("Duration", duration_label),
    ]
    if clean_reason:
        details.append(("Reason", clean_reason))

    intro = (
        f"A new permission request has been submitted by {employee_name} "
        "and requires your review."
    )
    intro_html = (
        "A new permission request has been submitted by "
        f"<b>{_html.escape(employee_name)}</b> and requires your review."
    )
    closing = (
        f"Please review the request and approve or reject it through "
        f"the {product} system."
    )
    return RenderedPermissionEmail(
        subject=f"Permission Request - {employee_name} - Action Required",
        text_body=_text_document(
            product=product,
            greeting=recipient_name,
            intro=intro,
            details=details,
            closing=closing,
            request_id=request_id,
            link=link,
        ),
        html_body=_html_document(
            product=product,
            greeting=recipient_name,
            intro_html=intro_html,
            details=details,
            closing=closing,
            request_id=request_id,
            link=link,
        ),
    )


def _text_document(
    *,
    product: str,
    greeting: str,
    intro: str,
    details: list[tuple[str, str]],
    closing: str,
    request_id: str,
    link: str | None,
) -> str:
    """The body of the permission email: a letter, not a layout - the same
    shape as `leave.email._text_document`."""
    lines = [f"Dear {greeting},", "", intro, ""]
    lines += [f"{label}: {value}" for label, value in details]
    lines += ["", closing]
    if link:
        lines += ["", "View Permission Request:", link]
    lines += [
        "",
        "Regards,",
        product,
        "",
        f"Request ID: {request_id}",
        "Automated notification - please do not reply.",
    ]
    return "\n".join(lines)


def _html_document(
    *,
    product: str,
    greeting: str,
    intro_html: str,
    details: list[tuple[str, str]],
    closing: str,
    request_id: str,
    link: str | None,
) -> str:
    """The same letter as `_text_document`, as the thinnest HTML that can carry
    a real hyperlink - see `leave.email._html_document` for the full rationale."""
    e = _html.escape

    paragraphs = [f"<p>Dear {e(greeting)},</p>", f"<p>{intro_html}</p>"]

    detail_lines = [
        f"{e(label)}: {'<b>' + e(value) + '</b>' if label == 'Duration' else e(value)}"
        for label, value in details
    ]
    if detail_lines:
        paragraphs.append(f"<p>{'<br>'.join(detail_lines)}</p>")

    paragraphs.append(f"<p>{e(closing)}</p>")

    if link:
        paragraphs.append(
            '<p><a href="{href}" '
            'style="color:#1155cc;text-decoration:underline;">'
            "<b>View Permission Request</b></a></p>".format(href=e(link, quote=True))
        )

    paragraphs.append(f"<p>Regards,<br>{e(product)}</p>")
    paragraphs.append(
        f"<p>Request ID: {e(request_id)}<br>"
        "Automated notification - please do not reply.</p>"
    )

    body = "\n".join(paragraphs)
    return (
        "<html><body "
        'style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'line-height:1.5;color:#000000;text-align:left;">\n'
        f"{body}\n"
        "</body></html>"
    )


# ---------- resolution + send ------------------------------------------------

def first_emailable(
    recipients: list[PermissionRecipient],
) -> PermissionRecipient | None:
    """The first candidate in the chain with a usable work email."""
    for candidate in recipients:
        if (candidate.employee.work_email or "").strip():
            return candidate
    return None


def send_submission_email(
    db: Session, employee: Employee, req: PermissionRequest
) -> None:
    """Queue the "please review this permission request" email. Never raises.

    Call AFTER the permission request is committed. Returns None whatever
    happens: a missing recipient, a disabled mailer, a down broker and an
    unexpected error are all logged and swallowed, because the request has
    already been saved and the in-app notification already delivered.
    """
    try:
        recipient = first_emailable(resolve_permission_recipients(db, employee, req))
        if recipient is None:
            logger.info(
                "permission_email.skipped reason=no_work_email permission_request=%s "
                "routed_project=%s",
                req.id,
                req.routed_project_id,
            )
            return

        rendered = render_submission_email(
            recipient_name=recipient.employee.full_name,
            employee_name=employee.full_name,
            permission_date=req.permission_date,
            duration_label=duration_label(req.duration_hours, req.period),
            reason=req.reason,
            request_id=str(req.id),
            link=build_link(permission_request_path(req)),
        )
        result = enqueue_email(
            to=recipient.employee.work_email,
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
        )

        if result.queued:
            logger.info(
                "permission_email.queued permission_request=%s routed_project=%s "
                "recipient=%s is_head=%s task_id=%s",
                req.id,
                req.routed_project_id,
                recipient.employee.employee_code,
                recipient.is_head,
                result.task_id,
            )
        else:
            logger.warning(
                "permission_email.not_queued reason=%s permission_request=%s "
                "routed_project=%s recipient=%s is_head=%s",
                result.reason,
                req.id,
                req.routed_project_id,
                recipient.employee.employee_code,
                recipient.is_head,
            )
    except Exception:  # noqa: BLE001 - a committed request must not fail here
        logger.exception("permission_email.failed permission_request=%s", req.id)
