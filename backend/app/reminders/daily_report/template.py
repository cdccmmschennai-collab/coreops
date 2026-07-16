"""Renders a PMReminder into an email subject + HTML + text + CSV attachment.

Responsibility (only): turn structured reminder data into a clean message. No
SMTP, no queries, no business rules.

Layout goals:
  * Employee ID and Employee Name are separate columns, followed by a Missing
    Days count and the dates themselves.
  * Missing dates are separated by a visible bullet (" • ") so Outlook never runs
    them together, even when it strips the cell styling.
  * The HTML is Outlook-safe: tables + inline CSS only, no flexbox, no grid, no
    external stylesheets, no JavaScript, no SVG, no banner artwork.
  * The plain-text fallback carries the same four columns and summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.core.config import settings
from app.reminders.daily_report.csv_report import build_csv, csv_filename
from app.reminders.daily_report.service import PMReminder

_DATE_FMT = "%d %b"                     # -> "06 Jul"
_SUBJECT_DATE_FMT = "%d %b %Y"          # -> "09 Jul 2026"
_STAMP_FMT = "%d %b %Y, %I:%M %p IST"   # -> "09 Jul 2026, 05:15 PM IST"
_DATE_SEP = " • "                       # bullet, keeps dates visibly separated

# India observes no DST, so a fixed +05:30 offset is exact and avoids depending
# on the tzdata package being present in the worker image.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str
    csv_filename: str
    csv_bytes: bytes


def render_daily_report_reminder(
    reminder: PMReminder, *, now: datetime | None = None
) -> RenderedEmail:
    product = settings.PRODUCT_NAME
    now = now or datetime.now(IST)
    today = now.date()
    # Address the PM by the name on their own record; each PM gets their own email.
    greeting = f"Hello {reminder.pm_name}"
    rows = _employee_rows(reminder)
    stamp = now.strftime(_STAMP_FMT)

    return RenderedEmail(
        subject=f"{product} | Outstanding Daily Reports | {today.strftime(_SUBJECT_DATE_FMT)}",
        html_body=_render_html(rows, reminder, product, greeting, stamp),
        text_body=_render_text(rows, reminder, product, greeting, stamp),
        csv_filename=csv_filename(today),
        csv_bytes=build_csv(rows, date_fmt=_DATE_FMT),
    )


def _employee_rows(reminder: PMReminder) -> list[tuple[str, str, int, list[date]]]:
    """Re-pivot (date -> employees) into one presentational row per employee.

    Collection logic is unchanged; this is presentation-only. Returns
    ``(code, name, missing_days, dates)`` sorted by employee name, each row's
    dates ascending. The HTML, the text fallback and the CSV are all built from
    this one list, so they cannot disagree.
    """
    by_key: dict[tuple[str, str], list[date]] = {}
    for day in reminder.days:
        for emp in day.employees:
            by_key.setdefault((emp.code, emp.name), []).append(day.report_date)

    rows = [
        (code, name, len(dates), sorted(dates))
        for (code, name), dates in by_key.items()
    ]
    rows.sort(key=lambda r: r[1].lower())
    return rows


def _pretty_dates(dates: list[date]) -> str:
    return _DATE_SEP.join(d.strftime(_DATE_FMT) for d in dates)


# -- plain-text fallback -----------------------------------------------------


def _render_text(
    rows: list[tuple[str, str, int, list[date]]],
    reminder: PMReminder,
    product: str,
    greeting: str,
    stamp: str,
) -> str:
    lines = [
        product,
        "Daily Reporting Compliance",
        "",
        f"{greeting},",
        "",
        f"The following employees have outstanding daily work reports as of {stamp}.",
        "",
        "Summary:",
        f"  Employees with Missing Reports: {len(rows)}",
        f"  Total Missing Report Days: {reminder.total_missing}",
        "",
        _text_table(rows),
        "",
        "The detailed list is attached as a CSV file and can be opened directly "
        "in Microsoft Excel.",
        "",
        "Please follow up with the respective employees and ask them to submit "
        "the pending reports.",
        "",
        "Regards,",
        product,
        "",
        "Automated notification - please do not reply.",
    ]
    return "\n".join(lines)


def _text_table(rows: list[tuple[str, str, int, list[date]]]) -> str:
    """Draw an ASCII box table with the same four columns as the HTML."""
    headers = ("Employee ID", "Employee Name", "Missing Days", "Missing Report Dates")
    cells = [
        (code, name, str(missing_days), _pretty_dates(dates))
        for code, name, missing_days, dates in rows
    ]
    widths = [
        max([len(headers[i])] + [len(row[i]) for row in cells]) for i in range(4)
    ]

    def border(fill: str) -> str:
        return "+" + "+".join(fill * (w + 2) for w in widths) + "+"

    def line(values: tuple[str, ...]) -> str:
        return "| " + " | ".join(v.ljust(widths[i]) for i, v in enumerate(values)) + " |"

    out = [border("-"), line(headers), border("=")]
    for row in cells:
        out.append(line(row))
        out.append(border("-"))
    return "\n".join(out)


# -- Outlook-safe HTML -------------------------------------------------------


def _render_html(
    rows: list[tuple[str, str, int, list[date]]],
    reminder: PMReminder,
    product: str,
    greeting: str,
    stamp: str,
) -> str:
    """Table-based, inline-CSS-only layout.

    Deliberately plain: white background, no hero banner, no colored branding
    block, no rounded cards, thin gray borders, compact spacing. The outer table
    + align="center" (plus the MSO ghost table) constrain the width to 700px in
    Outlook, which ignores max-width; modern clients use max-width:700px with
    width:100% to stay fluid on phones.
    """
    font = "Arial,'Segoe UI',Helvetica,sans-serif"
    cell = (
        "border:1px solid #d0d7de;padding:6px 10px;text-align:left;"
        "vertical-align:top;word-break:break-word;"
    )
    head_cell = f"{cell}background:#f2f2f2;font-weight:bold;"
    num_cell = f"{cell}text-align:center;"

    body_rows = "".join(
        f"<tr>"
        f'<td style="{cell}">{_escape(code)}</td>'
        f'<td style="{cell}">{_escape(name)}</td>'
        f'<td style="{num_cell}">{missing_days}</td>'
        f'<td style="{cell}">{_escape(_pretty_dates(dates))}</td>'
        f"</tr>"
        for code, name, missing_days, dates in rows
    )

    return f"""\
<div style="margin:0;padding:0;background:#ffffff;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;font-family:{font};">
    <tr>
      <td align="center" style="padding:0;">
        <!--[if mso]><table role="presentation" width="700" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
        <table role="presentation" align="center" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:700px;width:100%;margin:0 auto;">
          <tr>
            <td style="padding:20px;color:#1f2328;font-size:13px;line-height:1.45;font-family:{font};">
              <div style="font-size:13px;color:#57606a;font-weight:bold;">{_escape(product)}</div>
              <div style="font-size:17px;font-weight:bold;color:#1f2328;padding:2px 0 14px;">Daily Reporting Compliance</div>
              <p style="margin:0 0 10px;">{_escape(greeting)},</p>
              <p style="margin:0 0 14px;">The following employees have outstanding daily work reports as of {_escape(stamp)}.</p>
              <p style="margin:0 0 4px;font-weight:bold;">Summary:</p>
              <p style="margin:0 0 2px;">Employees with Missing Reports: <strong>{len(rows)}</strong></p>
              <p style="margin:0 0 14px;">Total Missing Report Days: <strong>{reminder.total_missing}</strong></p>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;font-size:13px;color:#1f2328;font-family:{font};">
                <tr>
                  <th width="14%" style="{head_cell}">Employee ID</th>
                  <th width="30%" style="{head_cell}">Employee Name</th>
                  <th width="12%" style="{head_cell}text-align:center;">Missing Days</th>
                  <th width="44%" style="{head_cell}">Missing Report Dates</th>
                </tr>
                {body_rows}
              </table>
              <p style="margin:16px 0 0;">The detailed list is attached as a CSV file and can be opened directly in Microsoft Excel.</p>
              <p style="margin:10px 0 0;">Please follow up with the respective employees and ask them to submit the pending reports.</p>
              <p style="margin:18px 0 0;">Regards,<br>{_escape(product)}</p>
              <p style="margin:18px 0 0;padding:10px 0 0;border-top:1px solid #e1e4e8;font-size:11px;color:#6a737d;">Automated notification - please do not reply.</p>
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
