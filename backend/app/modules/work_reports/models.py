"""Daily Work Report ORM models (mirrors employees/projects/attendance conventions).

A work report is a *header* — one row per (employee, report_date) — composed of one
or more *task lines* (work_report_tasks), each attributing time/counts to a project.

Operational records: no soft-delete. Only `draft` reports are hard-deletable (enforced
in the service layer); submitted/approved/rejected reports are retained. `total_minutes`
on the header is derived (sum of non-null task minutes), set server-side.

Extended in migration 0006 to carry the fields from the company's existing Google Form
daily report (day_status, location, counts, remarks, query_text, etc.).
"""
import enum
import uuid
from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class WorkReportStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"      # legacy — no longer produced (approval removed)
    rejected = "rejected"      # legacy — no longer produced ("Send back" removed)
    granted = "granted"        # the Project Head reopened the report on an edit request


class DayStatus(str, enum.Enum):
    # Company day-status taxonomy (replaces the original Google-Form placeholders
    # in migration 0048). The four NO-ACTIVITY statuses (leave, company_holiday,
    # week_off, comp_off) mean the employee did no project work that day — the
    # report carries no task lines, no benchmark, and no overdue/pending tracking.
    leave = "leave"
    company_holiday = "company_holiday"
    work_from_home = "work_from_home"
    week_off = "week_off"
    work_at_office = "work_at_office"
    half_day = "half_day"
    comp_off = "comp_off"
    overtime_compensation = "overtime_compensation"
    overtime_salary = "overtime_salary"
    permission_first_half_1hr = "permission_first_half_1hr"
    permission_second_half_1hr = "permission_second_half_1hr"
    permission_first_half_2hr = "permission_first_half_2hr"
    permission_second_half_2hr = "permission_second_half_2hr"


# Day statuses where the employee did no project work: the report needs no task
# lines and is exempt from benchmark / overdue / pending calculations.
NO_ACTIVITY_DAY_STATUSES = frozenset(
    {
        DayStatus.leave,
        DayStatus.company_holiday,
        DayStatus.week_off,
        DayStatus.comp_off,
    }
)


class WorkLocation(str, enum.Enum):
    hyderabad = "hyderabad"
    chennai = "chennai"
    qatar = "qatar"


class DailyWorkReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "daily_work_reports"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[WorkReportStatus] = mapped_column(
        SAEnum(
            WorkReportStatus,
            name="work_report_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=WorkReportStatus.draft.value,
    )
    # Google Form fields (migration 0006)
    day_status: Mapped[DayStatus | None] = mapped_column(
        SAEnum(DayStatus, name="day_status", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    location: Mapped[WorkLocation | None] = mapped_column(
        SAEnum(WorkLocation, name="work_location", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    well_head_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    pm_plant: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_list_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=text("0")
    )
    task_list_op_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=text("0")
    )
    maintenance_item_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=text("0")
    )
    maintenance_plan_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=text("0")
    )
    # Legacy field — kept for backward compat; new UI writes to `remarks` instead
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when the author requests edit access on a submitted (locked) report;
    # cleared when the Project Head grants the edit request or on resubmit.
    edit_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The author's reason for the edit request (shown to the Project Head).
    edit_request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "report_date", name="work_reports_emp_date_uq"),
        CheckConstraint(
            "total_minutes >= 0 AND total_minutes <= 1440", name="work_reports_total_minutes_range"
        ),
        Index("work_reports_employee_idx", "employee_id", "report_date"),
        Index("work_reports_status_idx", "status"),
        Index("work_reports_date_idx", "report_date"),
    )


class WorkItem(UUIDMixin, TimestampMixin, Base):
    """Persistent lifecycle record for a TASK_BASED (lumpsum) activity that may
    span several daily reports (migration 0056).

    A TASK_BASED activity is started on one report, may be *continued* on any
    number of later reports (dates need not be sequential), and completes once —
    possibly after its deadline. Before this table each daily entry was an
    independent work_report_tasks row with its own started/due date and its own
    completion flag, so continuing an activity silently reset its deadline and
    completion never spanned days. A WorkItem fixes that: it is the single,
    authoritative source for started_on / target_days / due_date / completed_on.
    The linked work_report_tasks rows mirror those fields for backward
    compatibility, but this row is the truth.

    due_date is FROZEN at creation (started_on + target_days - 1, calendar days)
    and never recomputed — a later change to the sub-activity's benchmark master
    must not move an in-flight deadline.

    The lifecycle (IN_PROGRESS / DUE_TODAY / OVERDUE / COMPLETED_ON_TIME /
    COMPLETED_LATE) is DERIVED from these dates on read (see
    work_items.service.lifecycle_of); it is deliberately NOT a stored, mutable
    status column. `completed_late` is likewise derived (completed_on > due_date),
    never stored.

    Scope: TASK_BASED only. NUMERIC daily-quantity benchmarks are inherently
    per-day and never produce a WorkItem.
    """
    __tablename__ = "work_items"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    sub_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    # started_on = the originating report's date. target_days snapshots the
    # sub-activity's benchmark_period_days at creation (>= 1). due_date is frozen.
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    target_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Display snapshots frozen at creation (same convention as work_report_tasks),
    # so the open-task list renders stable labels without extra joins.
    activity_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_activity_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("target_days >= 1", name="work_items_target_days_positive"),
        CheckConstraint("due_date >= started_on", name="work_items_due_after_start"),
        CheckConstraint(
            "completed_on IS NULL OR completed_on >= started_on",
            name="work_items_completed_after_start",
        ),
        Index("work_items_employee_idx", "employee_id"),
        Index("work_items_employee_sub_idx", "employee_id", "sub_activity_id"),
        Index("work_items_due_date_idx", "due_date"),
        # Open-task retrieval: unfinished items for one employee, by deadline.
        Index(
            "work_items_open_idx",
            "employee_id",
            "due_date",
            postgresql_where=text("completed_on IS NULL"),
        ),
    )


class WorkReportTask(UUIDMixin, Base):
    __tablename__ = "work_report_tasks"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_work_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # minutes_spent = project-activity hours; task_minutes_spent = task-based hours.
    # Both optional; both add to the report total.
    minutes_spent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_minutes_spent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    docs_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    bom_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spares_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Activity Master link (replaces free-text `activity_type` as the selection
    # mechanism going forward; `activity_type` itself is kept, auto-derived from
    # these for backward compat — see work_reports/service.py `_validate_tasks`).
    sub_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="SET NULL"), nullable=True
    )
    sub_activity_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot
    activity_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot (parent)
    # Frozen at submit time (submit_work_report -> _apply_benchmarks). Never
    # recomputed on draft save — only when the report is (re)submitted.
    benchmark_value_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    benchmark_period_days_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    benchmark_type_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Which of tags_count/docs_count/bom_count/spares_count fed the benchmark
    # calc, frozen at submit time (NUMERIC rows only). There is no separate
    # "actual count" field — the benchmark reads straight off the existing
    # count fields below so production numbers are never entered twice.
    relevant_count_field_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    deficit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    productivity_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    # TASK_BASED sub-activities only: no deficit/productivity calculation —
    # tracked by these dates instead. started_date/due_date are computed
    # server-side (see work_reports/service.py `_validate_tasks`), never
    # client-supplied. is_completed is the only real user input (the
    # completion checkbox / the dedicated completion-toggle endpoint);
    # completed_date is stamped automatically the moment it flips true.
    # is_overdue/days_overdue are NOT stored — computed fresh on every read
    # via activity_master.service.compute_overdue, so they're never stale.
    started_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Task-continuation link (migration 0056). When set, this row is one daily
    # entry of a WorkItem that may span several reports; started_date/due_date/
    # is_completed/completed_date above are mirrored from that authoritative
    # WorkItem inside the same transaction. NULL = a legacy standalone row
    # (pre-continuation behaviour, unchanged). RESTRICT: a WorkItem cannot be
    # deleted while report rows still reference it, so history is never
    # silently detached.
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=True
    )
    # Independent of the project's own assigned plant (projects.maintenance_plant_id)
    # — the employee picks which plant they actually worked at that day. Pick the
    # Maintenance Plant directly; Planning Plant code/description auto-derive and
    # are frozen as snapshots at save time, same convention as project_name/code.
    maintenance_plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_plants.id", ondelete="SET NULL"), nullable=True
    )
    maintenance_plant_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_plant_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    planning_plant_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    planning_plant_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Legacy Task-link columns — the Task module was removed (Phase 1). No longer
    # read/written; the FK to tasks was dropped from the model so the mapper does
    # not require the (now-gone) tasks table. Columns themselves are dropped in
    # migration 0053 (Task 7).
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    task_title: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot
    # Snapshot fields (migration 0017) — frozen at save time for historical accuracy.
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_job_code_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "minutes_spent IS NULL OR (minutes_spent >= 0 AND minutes_spent <= 1440)",
            name="work_report_tasks_minutes_range",
        ),
        Index("work_report_tasks_report_idx", "report_id"),
        Index("work_report_tasks_project_idx", "project_id"),
        Index("work_report_tasks_sub_activity_idx", "sub_activity_id"),
        Index("work_report_tasks_maintenance_plant_idx", "maintenance_plant_id"),
        Index("work_report_tasks_work_item_idx", "work_item_id"),
    )
