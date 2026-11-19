"""The "rework approval requested" email to the PM (Rework Activity Approval).

Same letter style as the leave emails: a plain-text body plus the thinnest HTML
twin, so "View Rework Request" can be a real link. One email per newly raised
request, sent only from rework_approvals.service.notify_new_requests, which runs
after the submit committed. Never raises.

There are no hours in CoreOps: the work's size is its DAY PART (Full Day /
First Half / Second Half), which is what the email states.

Recipient: the first PM in the routing list (reporting PM, else project PMs)
whose employee record has a work_email. User.email is a login identity and is
deliberately not used - the leave emails' rule.
"""
from __future__ import annotations

import html as _html
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.employees.models import Employee
from app.modules.leave.email import build_link
from app.modules.rework_approvals.models import ReworkApprovalRequest
from app.notifications.email_dispatch import enqueue_email

logger = logging.getLogger("coreops.rework_approvals.email")

_DATE_FMT = "%d %b %Y"
_LINK_TEXT = "View Rework Request"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str


def render_request_email(
    *,
    recipient_name: str,
    employee_code: str,
    employee_name: str,
    req: ReworkApprovalRequest,
    link: str | None,
) -> RenderedEmail:
    """Pure: everything comes in as arguments, so wording is testable."""
    from app.modules.rework_approvals.service import DAY_PART_LABEL

    product = settings.PRODUCT_NAME
    who = f"{employee_code} - {employee_name}" if employee_code else employee_name
    project = " - ".join(p for p in (req.project_code, req.project_name) if p) or "-"
    details = [
        ("Employee", who),
        ("Project", project),
        ("Reporting Date", req.report_date.strftime(_DATE_FMT)),
        ("Activity", req.activity_name or "-"),
        ("Sub-Activity", req.sub_activity_name),
        ("Day Part", DAY_PART_LABEL.get(req.day_part, req.day_part)),
        ("Employee Remarks", (req.employee_remarks or "").strip() or "-"),
    ]
    if req.cycle_no > 1:
        details.append(("Resubmission", f"Attempt {req.cycle_no}"))
    intro = (
        f"{employee_name} has submitted a rework activity that requires your approval."
    )
    closing = f"Please review the request and approve or reject it in {product}."

    text_lines = [f"Dear {recipient_name},", "", intro, ""]
    text_lines += [f"{label}: {value}" for label, value in details]
    text_lines += ["", closing]
    if link:
        text_lines += ["", f"{_LINK_TEXT}:", link]
    text_lines += [
        "", "Regards,", product, "",
        f"Request ID: {req.id}", "Automated notification - please do not reply.",
    ]

    e = _html.escape
    paragraphs = [
        f"<p>Dear {e(recipient_name)},</p>",
        f"<p><b>{e(employee_name)}</b> has submitted a rework activity that requires "
        "your approval.</p>",
        "<p>" + "<br>".join(f"{e(label)}: {e(value)}" for label, value in details) + "</p>",
        f"<p>{e(closing)}</p>",
    ]
    if link:
        paragraphs.append(
            f'<p><a href="{e(link, quote=True)}" '
            f'style="color:#1155cc;text-decoration:underline;"><b>{_LINK_TEXT}</b></a></p>'
        )
    paragraphs.append(f"<p>Regards,<br>{e(product)}</p>")
    paragraphs.append(
        f"<p>Request ID: {e(str(req.id))}<br>Automated notification - please do not reply.</p>"
    )
    html_body = (
        '<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;'
        'line-height:1.5;color:#000000;text-align:left;">\n'
        + "\n".join(paragraphs)
        + "\n</body></html>"
    )
    return RenderedEmail(
        subject=f"Rework Approval Request - {employee_name} - Action Required",
        text_body="\n".join(text_lines),
        html_body=html_body,
    )


def send_request_email(
    db: Session,
    employee: Employee,
    req: ReworkApprovalRequest,
    pm_user_ids: list[uuid.UUID],
) -> None:
    """Queue the email to the first routed PM with a work email. Never raises."""
    from app.modules.rework_approvals.service import detail_path

    try:
        recipient = None
        for uid in pm_user_ids:
            pm = db.execute(
                select(Employee)
                .where(Employee.user_id == uid, Employee.deleted_at.is_(None))
                .limit(1)
            ).scalars().first()
            if pm is not None and (pm.work_email or "").strip():
                recipient = pm
                break
        if recipient is None:
            logger.info("rework_email.skipped reason=no_work_email request=%s", req.id)
            return
        rendered = render_request_email(
            recipient_name=recipient.full_name,
            employee_code=employee.employee_code or "",
            employee_name=employee.full_name,
            req=req,
            link=build_link(detail_path(req.id)),
        )
        result = enqueue_email(
            to=recipient.work_email,
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
        )
        logger.info(
            "rework_email.%s request=%s recipient=%s reason=%s",
            "queued" if result.queued else "not_queued",
            req.id, recipient.employee_code, result.reason,
        )
    except Exception:  # noqa: BLE001 - never endanger the committed submit
        logger.exception("rework_email.failed request=%s", req.id)
