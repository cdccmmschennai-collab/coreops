"""Renders a PMReminder into an email subject + HTML + plain-text body.

Responsibility (only): turn structured reminder data into a clean message. No
SMTP, no queries, no business rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.config import settings
from app.reminders.daily_report.service import PMReminder

if TYPE_CHECKING:
    from datetime import date

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


def _employee_dates(reminder: PMReminder) -> list[tuple[str, list[date]]]:
    """Re-pivot the (date -> employees) collection into (employee -> dates).

    Collection logic is unchanged; this is a presentation-only regrouping so the
    email reads per employee. Employees are sorted by name, dates ascending.
    """
    by_name: dict[str, list[date]] = {}
    for day in reminder.days:
        for emp in day.employees:
            by_name.setdefault(emp.name, []).append(day.report_date)
    items = [(name, sorted(dates)) for name, dates in by_name.items()]
    items.sort(key=lambda x: x[0].lower())
    return items


def _date_chip(d: date, oldest: date | None) -> str:
    """A pill for one missing date. The most overdue date is highlighted red,
    the rest amber, so a manager's eye lands on the worst gap first."""
    label = d.strftime(_DATE_FMT)
    if oldest is not None and d == oldest:
        bg, fg, weight = "#fee2e2", "#b91c1c", "700"  # most overdue
    else:
        bg, fg, weight = "#fef3c7", "#b45309", "600"  # overdue
    return (
        f'<span style="display:inline-block;padding:3px 9px;margin:2px 6px 2px 0;'
        f"border-radius:6px;background:{bg};color:{fg};font-weight:{weight};"
        f'font-size:13px;line-height:1.5;white-space:nowrap;">{label}</span>'
    )


def _render_text(reminder: PMReminder, product: str, greeting: str) -> str:
    emp_items = _employee_dates(reminder)
    divider = "-" * 40
    lines = [
        f"{greeting},",
        "",
        "The following daily reports are still pending.",
        "",
        f"Employees checked:       {reminder.employees_checked}",
        f"Employees with missing:  {len(emp_items)}",
        f"Total missing entries:   {reminder.total_missing}",
        "",
        divider,
        "",
    ]
    for name, dates in emp_items:
        pretty = ", ".join(d.strftime(_DATE_FMT) for d in dates)
        lines.append(name)
        lines.append(f"  Missing: {pretty}")
        lines.append("")
    lines.append(divider)
    lines.append("")
    lines.append("Please follow up with the respective employees.")
    lines.append("")
    lines.append("Regards")
    lines.append(product)
    return "\n".join(lines)


def _render_html(reminder: PMReminder, product: str, greeting: str) -> str:
    emp_items = _employee_dates(reminder)
    all_dates = [d for _, dates in emp_items for d in dates]
    oldest = min(all_dates) if all_dates else None

    total_checked = reminder.employees_checked
    with_missing = len(emp_items)
    total_entries = reminder.total_missing

    rows = "".join(
        f'<tr>'
        f'<td style="padding:11px 16px;border:1px solid #e2e8f0;font-size:14px;'
        f'color:#0f172a;font-weight:600;vertical-align:top;">{_escape(name)}</td>'
        f'<td style="padding:9px 16px;border:1px solid #e2e8f0;font-size:14px;'
        f'vertical-align:top;">'
        f'{"".join(_date_chip(d, oldest) for d in dates)}</td>'
        f"</tr>"
        for name, dates in emp_items
    )

    def _stat(value: object, label: str, color: str, last: bool = False) -> str:
        border = "" if last else "border-right:1px solid #e2e8f0;"
        return (
            f'<td width="33.33%" style="padding:14px 8px;text-align:center;{border}">'
            f'<div style="font-size:22px;font-weight:700;color:{color};line-height:1;">{value}</div>'
            f'<div style="font-size:11px;color:#64748b;text-transform:uppercase;'
            f'letter-spacing:0.4px;margin-top:6px;">{label}</div></td>'
        )

    return f"""\
<div style="background:#f1f5f9;margin:0;padding:24px 12px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;">
    <tr><td>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#0f172a;padding:20px 24px;">
          <div style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:0.3px;">{_escape(product)}</div>
          <div style="color:#94a3b8;font-size:13px;margin-top:3px;">Outstanding Daily Reports</div>
        </td></tr>
        <tr><td style="padding:22px 24px 6px;">
          <p style="margin:0 0 4px;color:#0f172a;font-size:15px;">{_escape(greeting)},</p>
          <p style="margin:0;color:#475569;font-size:14px;line-height:1.5;">
            The following daily reports are still pending. Please follow up with the respective employees.
          </p>
        </td></tr>
        <tr><td style="padding:14px 24px 6px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:10px;">
            <tr>
              {_stat(total_checked, "Checked", "#0f172a")}
              {_stat(with_missing, "With Missing", "#b91c1c")}
              {_stat(total_entries, "Missing Entries", "#0f172a", last=True)}
            </tr>
          </table>
        </td></tr>
        <tr><td style="padding:12px 24px 6px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
            <tr>
              <th align="left" style="padding:10px 16px;background:#f8fafc;border:1px solid #e2e8f0;font-size:12px;color:#475569;text-transform:uppercase;letter-spacing:0.4px;font-weight:600;">Employee Name</th>
              <th align="left" style="padding:10px 16px;background:#f8fafc;border:1px solid #e2e8f0;font-size:12px;color:#475569;text-transform:uppercase;letter-spacing:0.4px;font-weight:600;">Missing Dates</th>
            </tr>
            {rows}
          </table>
        </td></tr>
        <tr><td style="padding:16px 24px 24px;">
          <p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.6;">Regards,<br>{_escape(product)}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>
"""


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
