"""Phase 3G - `origin` is readable by the client, and only readable.

The AUTO badge in the frontend is driven entirely by WorkReportOut.origin, so
the read schema has to carry it. Nothing else about the field changes: it is
still stamped by the generator alone (Phase 3C/3E) and never restamped by an
edit, because reconciliation matches on `origin = auto`.

These are schema-level tests on purpose - no DB, no HTTP. The generation and
reconciliation behaviour that produces the value is covered by
test_auto_weekend_reports.py / test_auto_leave_reports.py /
test_auto_report_reconciliation.py / test_auto_leave_reconciliation.py, and this
file must not duplicate or constrain any of it.
"""
import uuid
from datetime import date, datetime
from types import SimpleNamespace

from app.modules.work_reports.models import ReportOrigin, WorkReportStatus
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportOut,
    WorkReportUpdate,
)


def _row(**overrides):
    """A minimal stand-in for a DailyWorkReport ORM row (from_attributes)."""
    fields = dict(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        report_date=date(2026, 8, 22),
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        total_minutes=0,
        created_at=datetime(2026, 8, 22, 1, 0, 0),
        periods=[],
        tasks=[],
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_employee_report_serialises_as_employee_origin():
    out = WorkReportOut.model_validate(_row(origin=ReportOrigin.employee))
    assert out.origin == ReportOrigin.employee
    assert out.model_dump()["origin"] == ReportOrigin.employee


def test_auto_report_serialises_as_auto_origin():
    """The week-off / leave rows the 01:00 generator creates."""
    out = WorkReportOut.model_validate(_row(origin=ReportOrigin.auto))
    assert out.origin == ReportOrigin.auto


def test_edited_auto_report_still_reads_as_auto():
    """Editing reopens an automatic report to draft but never restamps origin -
    otherwise reconciliation would stop recognising its own row."""
    out = WorkReportOut.model_validate(
        _row(origin=ReportOrigin.auto, status=WorkReportStatus.draft)
    )
    assert out.status == WorkReportStatus.draft
    assert out.origin == ReportOrigin.auto


def test_origin_defaults_to_employee_when_absent():
    """A row read without the attribute (older fixtures/projections) must not
    blow up, and must never be reported as automatic."""
    row = _row()
    del row.origin
    assert WorkReportOut.model_validate(row).origin == ReportOrigin.employee


def test_origin_is_serialised_by_value_not_by_enum_name():
    """The frontend compares against the literal string "auto"."""
    dumped = WorkReportOut.model_validate(_row(origin=ReportOrigin.auto)).model_dump(mode="json")
    assert dumped["origin"] == "auto"


def test_origin_is_not_writable_by_the_client():
    """Read-only: the write schemas have no origin field, so a client that sends
    one cannot restamp a generated report as employee-authored."""
    assert "origin" not in WorkReportCreate.model_fields
    assert "origin" not in WorkReportUpdate.model_fields

    created = WorkReportCreate.model_validate(
        {"report_date": "2026-08-22", "origin": "employee"}
    )
    assert not hasattr(created, "origin")

    updated = WorkReportUpdate.model_validate({"origin": "employee"})
    assert not hasattr(updated, "origin")
