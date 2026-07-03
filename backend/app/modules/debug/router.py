"""Debug endpoints for the Daily Report Reminder pipeline.

  POST /debug/send-test-email   send a one-off test email (verify SMTP)
  GET  /debug/missing-reports   preview reminder data as JSON (verify grouping)
  POST /debug/send-reminders    run the reminder dispatcher immediately

All routes require the project_manager role and are only mounted when
ENABLE_DEBUG_ENDPOINTS=true.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.users.models import UserRole
from app.notifications.email_service import EmailSendError, EmailService
from app.reminders.daily_report.dispatcher import run_daily_report_reminders
from app.reminders.daily_report.service import DailyReportReminderService
from app.shared.errors import AppError

router = APIRouter(
    prefix="/debug",
    tags=["debug"],
    dependencies=[Depends(require_role(UserRole.project_manager))],
)


class TestEmailIn(BaseModel):
    to: str
    subject: str = "CoreOps • Test Email"
    message: str = "This is a CoreOps notification test email."


@router.post("/send-test-email")
def send_test_email(body: TestEmailIn) -> dict:
    html = (
        f'<div style="font-family:sans-serif;font-size:14px;color:#0f172a;">'
        f"{body.message}</div>"
    )
    try:
        sent = EmailService().send(
            to=str(body.to),
            subject=body.subject,
            html_body=html,
            text_body=body.message,
        )
    except EmailSendError as exc:
        raise AppError("email_failed", f"Test email failed: {exc}", 502)
    return {"sent": sent, "to": str(body.to)}


@router.get("/missing-reports")
def missing_reports(db: Session = Depends(get_db)) -> dict:
    reminders = DailyReportReminderService().collect(db)
    return {
        "pms_with_missing": len(reminders),
        "reminders": [
            {
                "pm_id": str(r.pm_id),
                "pm_name": r.pm_name,
                "pm_email": r.pm_email,
                "employees_checked": r.employees_checked,
                "total_missing": r.total_missing,
                "days": [
                    {
                        "date": day.report_date.isoformat(),
                        "employees": [e.name for e in day.employees],
                    }
                    for day in r.days
                ],
            }
            for r in reminders
        ],
    }


@router.post("/send-reminders")
def send_reminders(db: Session = Depends(get_db)) -> dict:
    result = run_daily_report_reminders(db=db)
    return {
        "pms_with_missing": result.pms_with_missing,
        "emails_sent": result.emails_sent,
        "emails_skipped": result.emails_skipped,
        "emails_failed": result.emails_failed,
        "total_missing": result.total_missing,
        "outcomes": [
            {
                "pm_email": o.pm_email,
                "employees_checked": o.employees_checked,
                "missing_found": o.missing_found,
                "email_sent": o.email_sent,
                "error": o.error,
            }
            for o in result.outcomes
        ],
    }
