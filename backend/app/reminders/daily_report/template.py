"""Renders a PMReminder into an email subject + HTML + text + CSV attachment.

Responsibility (only): turn structured reminder data into a clean message. No
SMTP, no queries, no business rules.

Layout goals:
  * Exactly one date is reported on — the previous working day — so every row
    carries the same single "Missing Report Date". There is no missing-days
    count and no multi-date cell.
  * The HTML is Outlook-safe: tables + inline CSS only, no flexbox, no grid, no
    external stylesheets, no JavaScript, no SVG, no banner artwork.
  * The plain-text fallback carries the same columns and summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.config import settings
from app.reminders.daily_report.csv_report import build_csv, csv_filename
from app.reminders.daily_report.service import PMReminder

_DATE_FMT = "%d %b %Y"          # -> "12 Aug 2026"
_SUBJECT_SEP = " • "       # bullet, matches the approved subject format
_CODE_NAME_SEP = " - "          # "EMP219 - ASKAR ALI K"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str
    csv_filename: str
    csv_bytes: bytes


def render_daily_report_reminder(reminder: PMReminder) -> RenderedEmail:
    product = settings.PRODUCT_NAME
    target = reminder.report_date
    target_label = target.strftime(_DATE_FMT)
    # Address the PM by the name on their own record; each PM gets their own email.
    greeting = f"Hello {reminder.pm_name}"
    rows = _employee_rows(reminder)

    return RenderedEmail(
        subject=_SUBJECT_SEP.join(
            [product, "Outstanding Daily Reports", target_label]
        ),
        html_body=_render_html(rows, product, greeting, target_label),
        text_body=_render_text(rows, product, greeting, target_label),
        csv_filename=csv_filename(target),
        csv_bytes=build_csv(rows, report_date=target, date_fmt=_DATE_FMT),
    )


def _employee_rows(reminder: PMReminder) -> list[tuple[str, str]]:
    """One presentational ``(code, name)`` row per employee, sorted by name.

    The HTML, the text fallback and the CSV are all built from this one list, so
    they cannot disagree. The date is the same for every row and lives on the
    reminder itself.
    """
    rows = [(emp.code, emp.name) for emp in reminder.employees]
    rows.sort(key=lambda r: r[1].lower())
    return rows


def _code_and_name(code: str, name: str) -> str:
    return f"{code}{_CODE_NAME_SEP}{name}" if code else name


# -- plain-text fallback -----------------------------------------------------


def _render_text(
    rows: list[tuple[str, str]],
    product: str,
    greeting: str,
    target_label: str,
) -> str:
    lines = [
        product,
        "Outstanding Daily Reports",
        "",
        f"{greeting},",
        "",
        "The following employees have not submitted their daily work report "
        f"for {target_label}.",
        "",
        f"Employees with Missing Reports: {len(rows)}",
        "",
        _text_table(rows, target_label),
        "",
        "The detailed list is attached as a CSV file and can be opened directly "
        "in Microsoft Excel.",
        "",
        "Please follow up with the respective employees and ask them to submit "
        "their pending report.",
        "",
        "Regards,",
        product,
        "",
        "Automated notification - please do not reply.",
    ]
    return "\n".join(lines)


def _text_table(rows: list[tuple[str, str]], target_label: str) -> str:
    """Two padded columns under a dashed rule."""
    headers = ("Employee ID & Name", "Missing Report Date")
    cells = [(_code_and_name(code, name), target_label) for code, name in rows]
    first_width = max([len(headers[0])] + [len(c[0]) for c in cells])
    gap = "    "

    out = [
        headers[0].ljust(first_width) + gap + headers[1],
        "-" * (first_width + len(gap) + len(headers[1])),
    ]
    out.extend(left.ljust(first_width) + gap + right for left, right in cells)
    return "\n".join(out)


# -- Outlook-safe HTML -------------------------------------------------------


def _render_html(
    rows: list[tuple[str, str]],
    product: str,
    greeting: str,
    target_label: str,
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

    body_rows = "".join(
        f"<tr>"
        f'<td style="{cell}">{_escape(_code_and_name(code, name))}</td>'
        f'<td style="{cell}">{_escape(target_label)}</td>'
        f"</tr>"
        for code, name in rows
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
              <div style="font-size:17px;font-weight:bold;color:#1f2328;padding:2px 0 14px;">Outstanding Daily Reports</div>
              <p style="margin:0 0 10px;">{_escape(greeting)},</p>
              <p style="margin:0 0 14px;">The following employees have not submitted their daily work report for {_escape(target_label)}.</p>
              <p style="margin:0 0 14px;">Employees with Missing Reports: <strong>{len(rows)}</strong></p>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;font-size:13px;color:#1f2328;font-family:{font};">
                <tr>
                  <th width="60%" style="{head_cell}">Employee ID &amp; Name</th>
                  <th width="40%" style="{head_cell}">Missing Report Date</th>
                </tr>
                {body_rows}
              </table>
              <p style="margin:16px 0 0;">The detailed list is attached as a CSV file and can be opened directly in Microsoft Excel.</p>
              <p style="margin:10px 0 0;">Please follow up with the respective employees and ask them to submit their pending report.</p>
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
