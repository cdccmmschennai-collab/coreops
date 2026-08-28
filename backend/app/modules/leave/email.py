"""The leave emails: "a request is waiting for you", and "your request was decided".

WHAT THIS SENDS, AND WHEN
=========================
Three messages, for exactly three events, each fired from one named call site in
`leave/service.py` and nowhere else:

  * SUBMISSION - an employee filed a request. Goes to the approver.
    `create_leave_request` -> :func:`send_submission_email`.
  * APPROVAL - a reviewer approved it. Goes to the requesting employee.
    `approve_leave_request` -> :func:`send_approval_email`.
  * REJECTION - a reviewer rejected it. Goes to the requesting employee.
    `reject_leave_request` -> :func:`send_rejection_email`.

Nothing else emails. Cancellation, cancellation requests and the two
cancellation decisions stay in-app only - which is why these live here rather
than as a branch inside `leave/service.py::_push`, the helper all six leave
notification events share. Attaching mail to `_push` would silently start
emailing every one of them.

PLAIN TEXT, PLUS THE THINNEST POSSIBLE HTML ALTERNATIVE
========================================================
All three are still, at heart, plain letters: a greeting, the facts, a link and a
signature. No tables, no containers, no buttons, no card, no banner, no brand
colours - a leave request is correspondence between two colleagues and must
arrive looking like an email a person typed in Outlook, not a designed
notification.

The one concession is the link. A bare URL sitting in the body is ugly and, worse,
a `text/plain` message cannot hide it behind words - "View Leave Request" can only
be the clickable text, and the CoreOps URL kept out of what the reader sees, if
there is an HTML part for the mail client to render. So each of these three now
carries a minimal HTML alternative alongside its text body: normal left-aligned
paragraphs in a normal font. Bold is spent on exactly three things - the actor
or outcome named in the opening sentence ("submitted by NAME", "approved by
NAME."), the Leave Period value, and the link text - never a field label, and
the link's only styling is `color:#1155cc; text-decoration:underline;`, a
plain blue underline, not a button. `_html_document` builds it; `_text_document`
is unchanged and still supplies the text/plain part non-HTML clients fall back
to, URL and all.

That HTML alternative is why these sends no longer pass `text_only=True` -
`enqueue_email` now gets both `text_body` and `html_body`, the same
multipart/alternative shape every other caller of the shared transport already
uses. The daily report reminder was never text_only and is untouched by this.

WHO EACH ONE GOES TO
====================
The submission email goes to the first candidate in
`leave/recipients.py::resolve_leave_recipients` that has a `work_email`: the
routed project's current Project Head, else the requester's reporting PM. That is
the SAME chain, in the same order, that the in-app notification walks - the two
channels differ only in the reachability test they apply to it (a login vs an
address), so they can never disagree about routing.

The decision emails go to ONE person and resolve no chain at all: the employee
named by `LeaveRequest.employee_id`. They are told the outcome of their own
request, so there is no fallback rung to fall through to - if that employee has
no work email, nobody else is a substitute and no mail is sent.

`Employee.work_email` is the only address any of them consults. `User.email` is a
login identity and is deliberately NOT used as a fallback: an employee's ability
to sign in says nothing about where their work mail should go. When no address
can be found, no email is sent and the in-app notification stands alone.

A fallback recipient is a DELIVERY decision only. Approval authority is
unchanged and lives in `leave/service.py::_assert_can_review`: the Project Head
remains the intended per-project approver even when the email went to the PM
instead - and the PM is authorized to review any request, so a fallback email
never lands with somebody who cannot act on it.

FAILURE IS NEVER THE CALLER'S PROBLEM
=====================================
Every `send_*` function here returns None and never raises. Each runs after the
decision it describes has already been committed, so nothing it does may
endanger that: an unresolvable recipient, a malformed payload, an unreachable
broker or a bug in the renderer all end as a log line. `enqueue_email` already
declines rather than raising for every delivery condition; the blanket `except`
covers the rest.

Delivery itself is asynchronous by construction - `enqueue_email` hands the
payload to Celery and returns. Nothing in the HTTP request path ever waits on
SMTP.
"""
from __future__ import annotations

import html as _html
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.employees.models import Employee
from app.modules.leave.models import LeaveRequest, LeaveType
from app.modules.leave.recipients import (
    LeaveRecipient,
    leave_request_path,
    resolve_leave_recipients,
)
from app.notifications.email_dispatch import enqueue_email

logger = logging.getLogger("coreops.leave.email")

# Matches the daily report reminder's format, so both CoreOps emails read the
# same way: "28 Aug 2026".
_DATE_FMT = "%d %b %Y"

# Display names for the stored enum. Mirrors the frontend's LEAVE_TYPE_LABEL
# (frontend/src/features/leave/types.ts) and adds the word "Leave" where it
# reads naturally: the UI shows "Casual" inside a column already headed "Type",
# while an email sentence has no such context. `comp_off` and `other` are left
# alone - "Comp Off Leave" and "Other Leave" read worse, not better.
_LEAVE_TYPE_LABELS: dict[LeaveType, str] = {
    LeaveType.casual: "Casual Leave",
    LeaveType.sick: "Sick Leave",
    LeaveType.annual: "Annual Leave",
    LeaveType.comp_off: "Comp Off",
    LeaveType.unpaid: "Unpaid Leave",
    LeaveType.other: "Other",
}


@dataclass(frozen=True)
class RenderedLeaveEmail:
    """One ready-to-send leave email: a text/plain body and its minimal HTML twin.

    `text_body` is the letter, exactly as before. `html_body` says the same
    things in the same order - it exists only so "View Leave Request" can be a
    real hyperlink instead of a bare URL; see the module docstring.
    """

    subject: str
    text_body: str
    html_body: str


# ---------- pure rendering --------------------------------------------------

def leave_type_label(leave_type: LeaveType) -> str:
    """Human label for a stored leave type, never the raw enum value."""
    return _LEAVE_TYPE_LABELS.get(leave_type, "Leave")


def leave_day_count(start: date, end: date) -> int:
    """Calendar days the request spans, inclusive of both ends.

    THE one day count every leave email quotes, so the submission mail and the
    decision mails can never state different lengths for the same request. It is
    deliberately the CALENDAR span of what the employee asked for - the same
    figure `LeaveRequest.start_date`/`end_date` show in the UI - and not
    `effects.leave_working_days`, which subtracts weekends and holidays to decide
    what the approval actually charges. Those two answer different questions:
    "how long is this absence" versus "what does it cost the balance", and the
    latter needs a database. Keeping this one pure is what lets the templates be
    tested without a session.
    """
    span = (end - start).days
    return span + 1 if span >= 0 else 0


def format_leave_period(start: date, end: date) -> str:
    """"28 Aug 2026 - 29 Aug 2026 (2 days)", or a single date for a one-day leave.

    A one-day leave rendered as a range reads like a mistake, so it is not, and
    the count is singular there: "28 Aug 2026 (1 day)".
    """
    days = leave_day_count(start, end)
    unit = "day" if days == 1 else "days"
    if start == end:
        return f"{start.strftime(_DATE_FMT)} ({days} {unit})"
    return (
        f"{start.strftime(_DATE_FMT)} - {end.strftime(_DATE_FMT)} "
        f"({days} {unit})"
    )


def build_link(path: str) -> str | None:
    """Absolute URL for an in-app path, or None when no public URL is configured.

    `APP_BASE_URL` is empty by default (local dev, tests, any deploy that has not
    set it), and a relative path in an inbox is a dead link - so the templates
    drop the whole call-to-action rather than render one. Trailing slashes on the
    configured value are tolerated.
    """
    base = (settings.APP_BASE_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}{path}"


def render_submission_email(
    *,
    recipient_name: str,
    employee_name: str,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    reason: str | None,
    request_id: str,
    link: str | None,
) -> RenderedLeaveEmail:
    """Turn one submitted leave request into a subject and a plain-text body.

    Pure: no database, no SMTP, no settings beyond the product name. Everything
    it needs is an argument, so the wording can be asserted in tests without a
    session or a mail server.

    The body greets the reader by name, names the employee, the leave type, the
    period and (when given) the reason, states plainly that the request needs
    review, and offers the link. Identifiers stay out of it: the request id
    appears once, in the footer, for support and audit, and the project routing
    that chose this recipient is never mentioned - the reader cares that a
    request is waiting, not how it arrived.
    """
    product = settings.PRODUCT_NAME
    clean_reason = (reason or "").strip()

    details = [
        ("Leave Type", leave_type_label(leave_type)),
        ("Leave Period", format_leave_period(start_date, end_date)),
    ]
    if clean_reason:
        details.append(("Reason", clean_reason))

    intro = (
        f"A new leave request has been submitted by {employee_name} "
        "and requires your review."
    )
    intro_html = (
        "A new leave request has been submitted by "
        f"<b>{_html.escape(employee_name)}</b> and requires your review."
    )
    closing = (
        f"Please review the request and approve or reject it through "
        f"the {product} system."
    )
    return RenderedLeaveEmail(
        subject=f"Leave Request - {employee_name} - Action Required",
        text_body=_text_document(
            product=product,
            greeting=recipient_name,
            intro=intro,
            details=details,
            note=None,
            closing=closing,
            request_id=request_id,
            link=link,
        ),
        html_body=_html_document(
            product=product,
            greeting=recipient_name,
            intro_html=intro_html,
            details=details,
            note=None,
            closing=closing,
            request_id=request_id,
            link=link,
        ),
    )


def render_decision_email(
    *,
    approved: bool,
    employee_name: str,
    reviewer_name: str | None,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    reason: str | None,
    reviewer_comment: str | None,
    request_id: str,
    link: str | None,
) -> RenderedLeaveEmail:
    """Turn one decided leave request into a subject and a plain-text body.

    Pure, exactly like :func:`render_submission_email`, and sharing its document
    shape so an approval, a rejection and a submission all read like mail from
    the same person.

    `approved` picks the whole voice of the message; the two outcomes are one
    function rather than two because everything except three sentences is
    identical, and splitting them is how the footer or the link rule ends up
    fixed in one copy and not the other.

    What the two outcomes deliberately do NOT share:

      * A REJECTION carries the employee's own reason and the reviewer's comment,
        because the reader is being told no and needs to see what was considered
        and what was said. Either is omitted entirely when absent - an empty
        "Reviewer Comment:" heading invites the reader to hunt for text that was
        never written, and no reason is ever invented to fill the gap.
      * An APPROVAL carries neither. The answer is yes; restating the reader's
        own words back at them adds nothing.

    `reviewer_name` is the actual decider. It is None only when the acting user
    has no employee record at all, and the sentence then simply drops the "by
    ..." clause rather than naming a placeholder.
    """
    product = settings.PRODUCT_NAME
    outcome = "approved" if approved else "rejected"

    details = [
        ("Leave Type", leave_type_label(leave_type)),
        ("Leave Period", format_leave_period(start_date, end_date)),
    ]
    clean_reason = (reason or "").strip()
    if not approved and clean_reason:
        details.append(("Reason", clean_reason))

    clean_comment = (reviewer_comment or "").strip()
    note = None
    if not approved and clean_comment:
        note = ("Reviewer Comment", clean_comment)

    if reviewer_name:
        intro = f"Your leave request has been {outcome} by {reviewer_name}."
        intro_html = (
            f"Your leave request has been <b>{outcome} by "
            f"{_html.escape(reviewer_name)}.</b>"
        )
    else:
        intro = f"Your leave request has been {outcome}."
        intro_html = f"Your leave request has been <b>{outcome}.</b>"

    if approved:
        closing = (
            f"Your leave request has been successfully approved in the "
            f"{product} system."
        )
    else:
        closing = (
            f"Please log in to the {product} system to view the request details."
        )

    return RenderedLeaveEmail(
        subject=f"Leave Request - {'Approved' if approved else 'Rejected'}",
        text_body=_text_document(
            product=product,
            greeting=employee_name,
            intro=intro,
            details=details,
            note=note,
            closing=closing,
            request_id=request_id,
            link=link,
        ),
        html_body=_html_document(
            product=product,
            greeting=employee_name,
            intro_html=intro_html,
            details=details,
            note=note,
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
    note: tuple[str, str] | None,
    closing: str,
    request_id: str,
    link: str | None,
) -> str:
    """The body of every leave email: a letter, not a layout.

    One shape for all three messages - greeting, one sentence saying what
    happened, the facts as `Label: value` lines, an optional note, one closing
    sentence, the link, the sign-off, and a quiet footer. Nothing here emits
    markup; the string this returns is exactly what lands in the recipient's
    inbox.

    The URL sits on its own line under `View Leave Request:` so that mail clients
    that wrap long lines cannot break the link in half, and so the reader can
    select it cleanly. When there is no link, the whole call-to-action is
    dropped rather than left dangling.
    """
    lines = [f"Dear {greeting},", "", intro, ""]
    lines += [f"{label}: {value}" for label, value in details]
    if note is not None:
        lines += ["", f"{note[0]}: {note[1]}"]
    lines += ["", closing]
    if link:
        lines += ["", "View Leave Request:", link]
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
    note: tuple[str, str] | None,
    closing: str,
    request_id: str,
    link: str | None,
) -> str:
    """The same letter as `_text_document`, as the thinnest HTML that can carry
    a real hyperlink.

    Existing exclusively so "View Leave Request" can be clickable text with the
    CoreOps URL hidden behind it - a `text/plain` part cannot do that at all. No
    table, no div, no card, no background, no button: plain left-aligned
    paragraphs in the browser/client default font. Bold is spent on exactly
    three things - the actor/outcome clause in the opening sentence (built into
    `intro_html` by the caller, since only it knows which words that is), the
    Leave Period value, and the link text - never a field label. The anchor is
    the only element with any inline style, `color:#1155cc;
    text-decoration:underline;`, a plain blue underline rather than a button.
    Every value that did not come from this module is escaped, since a leave
    reason or a name is free text typed by an employee; `intro_html` is the one
    exception because the caller has already escaped its dynamic pieces.
    """
    e = _html.escape

    paragraphs = [f"<p>Dear {e(greeting)},</p>", f"<p>{intro_html}</p>"]

    detail_lines = []
    for label, value in details:
        rendered_value = f"<b>{e(value)}</b>" if label == "Leave Period" else e(value)
        detail_lines.append(f"{e(label)}: {rendered_value}")
    if detail_lines:
        paragraphs.append(f"<p>{'<br>'.join(detail_lines)}</p>")
    if note is not None:
        paragraphs.append(f"<p>{e(note[0])}: {e(note[1])}</p>")

    paragraphs.append(f"<p>{e(closing)}</p>")

    if link:
        paragraphs.append(
            '<p><a href="{href}" '
            'style="color:#1155cc;text-decoration:underline;">'
            "<b>View Leave Request</b></a></p>".format(href=e(link, quote=True))
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


# ---------- resolution + send ----------------------------------------------

def first_emailable(recipients: list[LeaveRecipient]) -> LeaveRecipient | None:
    """The first candidate in the chain with a usable work email.

    `work_email` is nullable and, being free text from the employee record, can
    be blank, so it is stripped before being believed.
    """
    for candidate in recipients:
        if (candidate.employee.work_email or "").strip():
            return candidate
    return None


def send_submission_email(db: Session, employee: Employee, req: LeaveRequest) -> None:
    """Queue the "please review this leave request" email. Never raises.

    Call AFTER the leave request is committed. Returns None whatever happens: a
    missing recipient, a disabled mailer, a down broker and an unexpected error
    are all logged and swallowed, because the request they describe has already
    been saved and the in-app notification has already been delivered.
    """
    try:
        recipient = first_emailable(resolve_leave_recipients(db, employee, req))
        if recipient is None:
            logger.info(
                "leave_email.skipped reason=no_work_email leave_request=%s "
                "routed_project=%s",
                req.id,
                req.routed_project_id,
            )
            return

        rendered = render_submission_email(
            recipient_name=recipient.employee.full_name,
            employee_name=employee.full_name,
            leave_type=req.leave_type,
            start_date=req.start_date,
            end_date=req.end_date,
            reason=req.reason,
            request_id=str(req.id),
            link=build_link(
                leave_request_path(req, is_head=recipient.is_head)
            ),
        )
        result = enqueue_email(
            to=recipient.employee.work_email,
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
        )

        # Logged at the FEATURE level as well as inside enqueue_email, because
        # the transport log cannot say which routing decision produced the
        # address - "the Head, or the fallback" is the question asked when an
        # email is reported missing.
        if result.queued:
            logger.info(
                "leave_email.queued leave_request=%s routed_project=%s "
                "recipient=%s is_head=%s task_id=%s",
                req.id,
                req.routed_project_id,
                recipient.employee.employee_code,
                recipient.is_head,
                result.task_id,
            )
        else:
            logger.warning(
                "leave_email.not_queued reason=%s leave_request=%s "
                "routed_project=%s recipient=%s is_head=%s",
                result.reason,
                req.id,
                req.routed_project_id,
                recipient.employee.employee_code,
                recipient.is_head,
            )
    except Exception:  # noqa: BLE001 - a committed leave request must not fail here
        logger.exception("leave_email.failed leave_request=%s", req.id)


def send_approval_email(
    db: Session, req: LeaveRequest, reviewer: Employee | None
) -> None:
    """Queue the "your leave request was approved" email. Never raises.

    Call from `approve_leave_request` ONLY, after the commit and after the
    in-app `leave_approved` notification.
    """
    _send_decision_email(db, req, reviewer, approved=True)


def send_rejection_email(
    db: Session, req: LeaveRequest, reviewer: Employee | None
) -> None:
    """Queue the "your leave request was rejected" email. Never raises.

    Call from `reject_leave_request` ONLY, after the commit and after the in-app
    `leave_rejected` notification.
    """
    _send_decision_email(db, req, reviewer, approved=False)


def _send_decision_email(
    db: Session, req: LeaveRequest, reviewer: Employee | None, *, approved: bool
) -> None:
    """Resolve the requesting employee, render the outcome, queue it. Never raises.

    Reached from exactly two call sites - `approve_leave_request` and
    `reject_leave_request`, each of which has already refused any request that
    was not `pending`, so a request can produce at most one decision email in its
    lifetime. It is deliberately NOT reachable from `_push`, `_notify_employee`
    or `_notify_routed_approver`: those are shared by the cancellation events,
    which do not email at all.

    The recipient is `req.employee_id` and nothing else. No chain is walked and
    no fallback exists - the message is about the reader's own request, so there
    is nobody to redirect it to. `Employee.work_email` is the only address
    consulted; a null or blank one means no email, while the decision itself and
    its in-app notification stand exactly as they are.
    """
    outcome = "approved" if approved else "rejected"
    try:
        employee = db.get(Employee, req.employee_id)
        address = (employee.work_email or "").strip() if employee else ""
        if not address:
            logger.info(
                "leave_decision_email.skipped reason=no_work_email outcome=%s "
                "leave_request=%s employee=%s",
                outcome,
                req.id,
                req.employee_id,
            )
            return

        rendered = render_decision_email(
            approved=approved,
            employee_name=employee.full_name,
            reviewer_name=reviewer.full_name if reviewer else None,
            leave_type=req.leave_type,
            start_date=req.start_date,
            end_date=req.end_date,
            reason=req.reason,
            reviewer_comment=req.manager_comment,
            request_id=str(req.id),
            # The rung the EMPLOYEE reads their own request at - the same path
            # the `leave_approved` / `leave_rejected` notification deep-links to,
            # built by the same helper so the bell and the inbox cannot drift.
            link=build_link(leave_request_path(req, is_head=False)),
        )
        result = enqueue_email(
            to=address,
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
        )

        if result.queued:
            logger.info(
                "leave_decision_email.queued outcome=%s leave_request=%s "
                "employee=%s task_id=%s",
                outcome,
                req.id,
                employee.employee_code,
                result.task_id,
            )
        else:
            logger.warning(
                "leave_decision_email.not_queued reason=%s outcome=%s "
                "leave_request=%s employee=%s",
                result.reason,
                outcome,
                req.id,
                employee.employee_code,
            )
    except Exception:  # noqa: BLE001 - a committed decision must not fail here
        logger.exception(
            "leave_decision_email.failed outcome=%s leave_request=%s",
            outcome,
            req.id,
        )
