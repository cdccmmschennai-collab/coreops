"""Renders a PMReminder into an email subject + HTML + plain-text body.

Responsibility (only): turn structured reminder data into a clean message. No
SMTP, no queries, no business rules.

Layout goals:
  * First column is "<Employee ID> <Name>" (e.g. "EMP225 Santhosh Kumar K").
  * Missing dates are separated by a visible bullet (" • ") so they never run
    together, even when a mail client strips the cell styling.
  * HTML renders as a bordered, Excel-style grid; the plain-text fallback draws
    the same grid with ASCII box characters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings
from app.reminders.daily_report.service import PMReminder

if TYPE_CHECKING:
    from datetime import date, datetime

_DATE_FMT = "%d %b"       # -> "06 Jul"
_DATE_SEP = " • "    # " • " bullet, keeps dates visibly separated


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str


def render_daily_report_reminder(
    reminder: PMReminder, *, now: datetime | None = None
) -> RenderedEmail:
    product = settings.PRODUCT_NAME
    subject = f"{product} • Outstanding Daily Reports"
    # Address the PM by the name on their own record; each PM gets their own email.
    greeting = f"Hello {reminder.pm_name}"
    return RenderedEmail(
        subject=subject,
        html_body=_render_html(reminder, product, greeting),
        text_body=_render_text(reminder, product, greeting),
    )


def _employee_rows(reminder: PMReminder) -> list[tuple[str, str]]:
    """Re-pivot (date -> employees) into one presentational row per employee.

    Collection logic is unchanged; this is presentation-only. Returns a list of
    ``(label, dates)`` where ``label`` is "<code> <name>" and ``dates`` is the
    employee's missing dates joined by the bullet separator. Rows are sorted by
    employee name; each employee's dates are ascending.
    """
    by_key: dict[tuple[str, str], list[date]] = {}
    for day in reminder.days:
        for emp in day.employees:
            by_key.setdefault((emp.code, emp.name), []).append(day.report_date)

    rows: list[tuple[str, str, str]] = []
    for (code, name), dates in by_key.items():
        label = f"{code} {name}".strip()
        pretty = _DATE_SEP.join(d.strftime(_DATE_FMT) for d in sorted(dates))
        rows.append((name, label, pretty))
    rows.sort(key=lambda r: r[0].lower())
    return [(label, dates) for _name, label, dates in rows]


# -- plain-text (ASCII grid) fallback ---------------------------------------


def _render_text(reminder: PMReminder, product: str, greeting: str) -> str:
    rows = _employee_rows(reminder)
    table = _text_table(rows)
    lines = [
        f"{greeting},",
        "",
        "The following employees have pending daily work reports.",
        "",
        table,
        "",
        f"Employees with Missing Reports : {len(rows)}",
        f"Total Missing Report Days : {reminder.total_missing}",
        "",
        "Regards,",
        product,
    ]
    return "\n".join(lines)


def _text_table(rows: list[tuple[str, str]]) -> str:
    """Draw an ASCII box table with two columns and dynamic widths."""
    h0, h1 = "Employee ID & Name", "Missing Report Dates"
    w0 = max([len(h0)] + [len(label) for label, _ in rows])
    w1 = max([len(h1)] + [len(dates) for _, dates in rows])

    def border(fill: str) -> str:
        return f"+{fill * (w0 + 2)}+{fill * (w1 + 2)}+"

    def line(a: str, b: str) -> str:
        return f"| {a.ljust(w0)} | {b.ljust(w1)} |"

    out = [border("-"), line(h0, h1), border("=")]
    for label, dates in rows:
        out.append(line(label, dates))
        out.append(border("-"))
    return "\n".join(out)


# -- HTML (Excel-style grid) -------------------------------------------------


def _render_html(reminder: PMReminder, product: str, greeting: str) -> str:
    """A flat internal-notification layout (Outlook/GitHub style).

    Deliberately plain: white background, no hero banner, no colored branding
    blocks, no rounded cards, thin table borders, and minimal spacing.
    """
    rows = _employee_rows(reminder)
    emp_with_missing = len(rows)
    total_missing_days = reminder.total_missing

    cell = (
        "border:1px solid #d0d7de;padding:8px 12px;text-align:left;"
        "vertical-align:top;word-break:break-word;"
    )
    head_cell = f"{cell}background:#f6f8fa;font-weight:700;"
    body_rows = "".join(
        f"<tr>"
        f'<td style="{cell}">{_escape(label)}</td>'
        f'<td style="{cell}">{_escape(dates)}</td>'
        f"</tr>"
        for label, dates in rows
    )

    # Centered, fixed-width container. The outer table + align="center" (plus the
    # MSO ghost table) constrain the width to 700px in Outlook, which ignores
    # max-width; modern clients use max-width:700px / width:100% to stay fluid.
    return f"""\
<div style="margin:0;padding:0;background:#ffffff;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <tr>
      <td align="center" style="padding:0;">
        <!--[if mso]><table role="presentation" width="700" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
        <table role="presentation" align="center" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:700px;width:100%;margin:0 auto;">
          <tr>
            <td style="padding:24px;color:#1f2328;font-size:14px;line-height:1.5;">
              <div style="font-size:13px;color:#57606a;font-weight:600;">{_escape(product)}</div>
              <div style="font-size:18px;font-weight:700;color:#1f2328;margin:2px 0 18px;">Outstanding Daily Reports</div>
              <p style="margin:0 0 12px;">{_escape(greeting)},</p>
              <p style="margin:0 0 18px;">The following employees have pending daily work reports.</p>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;font-size:13px;color:#1f2328;">
                <tr>
                  <th width="65%" style="{head_cell}">Employee ID &amp; Name</th>
                  <th width="35%" style="{head_cell}">Missing Report Dates</th>
                </tr>
                {body_rows}
              </table>
              <p style="margin:22px 0 0;">Employees with Missing Reports : <strong>{emp_with_missing}</strong></p>
              <p style="margin:4px 0 0;">Total Missing Report Days : <strong>{total_missing_days}</strong></p>
              <p style="margin:24px 0 0;">Regards,<br>{_escape(product)}</p>
            </td>
          </tr>
        </table>
        <!--[if mso]></td></tr></table><![endif]-->
      </td>
    </tr>
  </table>
</div>
"""


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
