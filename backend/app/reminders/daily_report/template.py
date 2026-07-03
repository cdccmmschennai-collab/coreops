"""Renders a PMReminder into an email subject + HTML + plain-text body.

Responsibility (only): turn structured reminder data into a clean message. No
SMTP, no queries, no business rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings
from app.reminders.daily_report.service import PMReminder

_DATE_FMT = "%d %b"  # -> "03 Jul"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str


def _greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def render_daily_report_reminder(
    reminder: PMReminder, *, now: datetime | None = None
) -> RenderedEmail:
    product = settings.PRODUCT_NAME
    subject = f"{product} • Outstanding Daily Reports"
    greeting = f"{_greeting(now)} {reminder.pm_name}"
    return RenderedEmail(
        subject=subject,
        html_body=_render_html(reminder, product, greeting),
        text_body=_render_text(reminder, product, greeting),
    )


def _render_text(reminder: PMReminder, product: str, greeting: str) -> str:
    lines = [
        f"{greeting},",
        "",
        "The following daily reports are still pending.",
        "",
    ]
    divider = "-" * 32
    for day in reminder.days:
        lines.append(divider)
        lines.append("")
        lines.append(day.report_date.strftime(_DATE_FMT))
        lines.append("")
        for emp in day.employees:
            lines.append(f"  • {emp.name}")
        lines.append("")
    lines.append(divider)
    lines.append("")
    lines.append("Please follow up with the respective employees.")
    lines.append("")
    lines.append("Regards")
    lines.append(product)
    return "\n".join(lines)


def _render_html(reminder: PMReminder, product: str, greeting: str) -> str:
    sections: list[str] = []
    for day in reminder.days:
        items = "".join(
            f'<li style="margin:2px 0;">{_escape(emp.name)}</li>'
            for emp in day.employees
        )
        sections.append(
            f"""
            <div style="border-top:1px solid #e2e8f0;padding:16px 0;">
              <div style="font-weight:600;color:#0f172a;font-size:15px;margin-bottom:8px;">
                {day.report_date.strftime(_DATE_FMT)}
              </div>
              <ul style="margin:0;padding-left:20px;color:#334155;font-size:14px;">
                {items}
              </ul>
            </div>
            """
        )
    body = "".join(sections)
    return f"""\
<div style="background:#f1f5f9;padding:24px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;
              overflow:hidden;border:1px solid #e2e8f0;">
    <div style="background:#0f172a;color:#ffffff;padding:18px 24px;font-size:16px;font-weight:600;">
      {_escape(product)} • Outstanding Daily Reports
    </div>
    <div style="padding:24px;">
      <p style="margin:0 0 8px;color:#0f172a;font-size:15px;">{_escape(greeting)},</p>
      <p style="margin:0 0 8px;color:#334155;font-size:14px;">
        The following daily reports are still pending.
      </p>
      {body}
      <div style="border-top:1px solid #e2e8f0;padding-top:16px;margin-top:4px;
                  color:#334155;font-size:14px;">
        Please follow up with the respective employees.
      </div>
      <p style="margin:24px 0 0;color:#64748b;font-size:13px;">Regards<br>{_escape(product)}</p>
    </div>
  </div>
</div>
"""


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
