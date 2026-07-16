"""Local-only smoke test for the Daily Report Reminder email.

Purpose: verify the *rendered* reminder email (especially the new
"Hello <Manager Name>," greeting) against real database data, without ever
touching a real PM's inbox and without changing any production behaviour.

What it reuses (unchanged):
  - DailyReportReminderService().collect(db)  -> the exact same missing-report
    data the scheduled task would compute.
  - render_daily_report_reminder(...)         -> the exact same email template.
  - EmailService().send(...)                  -> the exact same SMTP transport.

What it deliberately overrides:
  - The recipient. Every email is redirected to TEST_RECIPIENT
    (cdccmmschennai@gmail.com). The real PM email is only PRINTED, never used as
    a destination. There is no code path in this script that sends to pm_email.

What it does NOT touch:
  - The Celery schedule, the periodic task, the dispatcher's per-PM grouping,
    and the SMTP configuration are all left exactly as they are. This script is
    a standalone entrypoint; production keeps sending each PM their own email.

Usage (inside the backend container):

  # Dry run — collect + render + verify greeting, but send nothing:
  python -m scripts.test_daily_report_reminder_email --dry-run

  # Real send — deliver every rendered email to the test inbox only:
  python -m scripts.test_daily_report_reminder_email --send

  # Optionally pin the "today" the window is computed from (default: today):
  python -m scripts.test_daily_report_reminder_email --dry-run --today 2026-07-27

A real send additionally requires EMAIL_ENABLED=true and a configured SMTP
(SMTP_HOST / SMTP_FROM), same as the production task.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.notifications.email_service import Attachment, EmailSendError, EmailService
from app.reminders.daily_report.service import DailyReportReminderService, PMReminder
from app.reminders.daily_report.template import render_daily_report_reminder

# Hard-coded test destination. Every email this script sends goes here and
# nowhere else. Do not parameterise this to a PM address.
TEST_RECIPIENT = "santhoshkumar.g@cdci-india.com"


def _expected_greeting(reminder: PMReminder) -> str:
    return f"Hello {reminder.pm_name},"


def _greeting_line(rendered) -> str:
    """The 'Hello <Manager Name>,' line from the text body ('' if absent)."""
    for line in rendered.text_body.splitlines():
        if line.startswith("Hello "):
            return line
    return ""


def _check_greeting(reminder: PMReminder, rendered) -> bool:
    """The text body and the HTML must both greet the PM by name."""
    expected = _expected_greeting(reminder)
    text_ok = _greeting_line(rendered) == expected
    html_ok = f"Hello {reminder.pm_name}" in rendered.html_body
    return text_ok and html_ok


def _print_reminder(reminder: PMReminder, rendered, greeting_ok: bool) -> None:
    print("-" * 60)
    print(f"  Original PM name  : {reminder.pm_name}")
    print(f"  Original PM email : {reminder.pm_email}   (NOT a recipient)")
    print(f"  Test recipient    : {TEST_RECIPIENT}")
    print(f"  Employees checked : {reminder.employees_checked}")
    print(f"  Missing reports   : {reminder.total_missing}")
    print(f"  Subject           : {rendered.subject}")
    print(f"  Greeting line     : {_greeting_line(rendered)}")
    print(f"  CSV attachment    : {rendered.csv_filename} "
          f"({len(rendered.csv_bytes)} bytes)")
    status = "PASS" if greeting_ok else "FAIL"
    print(f"  Greeting 'Hello {reminder.pm_name},' -> {status}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local-only test of the daily report reminder email "
        f"(always delivered to {TEST_RECIPIENT})."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect + render + verify the greeting, but send NOTHING (default).",
    )
    mode.add_argument(
        "--send",
        action="store_true",
        help=f"Actually send every rendered email to {TEST_RECIPIENT} (test inbox).",
    )
    parser.add_argument(
        "--today",
        help="Compute the missing-report window as of this date (YYYY-MM-DD). "
        "Defaults to today.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Send at most N emails to the test inbox (default 1). Rendering and "
        "the greeting check still run for every PM. Use 0 for no cap.",
    )
    args = parser.parse_args()

    # Default to dry-run unless --send is explicitly given.
    send = bool(args.send)

    today: date | None = None
    if args.today:
        try:
            today = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit(f"Invalid --today (expected YYYY-MM-DD): {args.today!r}")

    mode_label = "SEND (to test inbox only)" if send else "DRY-RUN (no email sent)"
    print(f"Daily Report Reminder email test")
    print(f"Mode           : {mode_label}")
    print(f"Test recipient : {TEST_RECIPIENT}")
    print(f"Window as of   : {today or date.today()}")

    with SessionLocal() as db:
        reminders = DailyReportReminderService().collect(db, today=today)

    if not reminders:
        print(
            "\nNo PMs currently have missing reports for this window — nothing to "
            "render or send. Try a different --today, or add a missing report."
        )
        return 0

    email_service = EmailService() if send else None
    all_greetings_ok = True
    sent_count = 0
    skipped_count = 0
    failed_count = 0

    print(f"\nPMs with missing reports: {len(reminders)}")
    for reminder in reminders:
        rendered = render_daily_report_reminder(reminder)
        greeting_ok = _check_greeting(reminder, rendered)
        all_greetings_ok = all_greetings_ok and greeting_ok
        _print_reminder(reminder, rendered, greeting_ok)

        if not send:
            print("  Action            : DRY-RUN - not sent")
            continue

        if args.limit and sent_count >= args.limit:
            print(f"  Action            : SKIPPED (--limit {args.limit} reached)")
            continue

        # The ONLY destination is the test inbox. reminder.pm_email is never used.
        try:
            was_sent = email_service.send(
                to=TEST_RECIPIENT,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                attachments=[
                    Attachment(
                        filename=rendered.csv_filename,
                        content=rendered.csv_bytes,
                        maintype="text",
                        subtype="csv",
                    )
                ],
            )
        except EmailSendError as exc:
            failed_count += 1
            print(f"  Action            : SEND FAILED -> {exc}")
            continue

        if was_sent:
            sent_count += 1
            print(f"  Action            : SENT to {TEST_RECIPIENT}")
        else:
            skipped_count += 1
            print(
                "  Action            : SKIPPED (email disabled / SMTP not "
                "configured — set EMAIL_ENABLED=true and SMTP_HOST/SMTP_FROM)"
            )

    print("-" * 60)
    print("Summary")
    print(f"  PMs processed        : {len(reminders)}")
    if send:
        print(f"  Emails sent (test)   : {sent_count}")
        print(f"  Emails skipped       : {skipped_count}")
        print(f"  Emails failed        : {failed_count}")
    else:
        print("  Emails sent          : 0 (dry-run)")
    print(f"  Greeting check       : {'PASS' if all_greetings_ok else 'FAIL'}")

    return 0 if all_greetings_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
