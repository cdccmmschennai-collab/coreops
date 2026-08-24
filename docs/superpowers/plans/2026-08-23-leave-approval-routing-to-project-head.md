# Leave Approval Routing to Project Head (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route a new leave request to the Project Head of the project the employee actually worked on during their previous working day (per their Daily Work Report), falling back to the existing PM approval flow when no such Head exists — without changing any existing Employee or PM leave behavior.

**Architecture:** Add one nullable `routed_project_id` column to `leave_requests`, resolved once at creation time by a small new `leave/routing.py` service (previous working day → that day's Daily Work Report → its one unambiguous project). Everything downstream — "who may see/approve this request", "who gets notified" — re-reads the **current** `Project.head_employee_id` for that column at read/notify/approve time via the Project-Head authorization helpers that already exist in `app/core/authz.py` (built for Work Reports and already battle-tested there). No new role, no new permission system, no new endpoints: the existing `/leave-requests/*` endpoints, `LeaveManagementPanel`, and notification pipeline are reused as-is, with the PM-only gates widened to "PM or the routed project's current Head".

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), Next.js + React Query + shadcn Tabs (frontend), pytest (backend tests).

**Spec:** The full Phase 1 spec is the "Phase 1 — Leave Approval Routing to Project Head" instructions in this conversation's system prompt (no separate spec file exists in the repo — this plan **is** the translation of that spec into code). Re-read that spec alongside this plan; this plan does not repeat its narrative, only its binding rules below.

## Global Constraints

- **Phase 1 only.** Do NOT implement: lump-sum / `NON_QUANTITATIVE` activity continuation, email notifications, a Head-specific redesign of the employee Leave UI, new endpoints beyond what a task below calls for, or any change to Daily Report behavior unrelated to resolving the previous working day's project.
- **In-app notifications only** — reuse `app.modules.notifications.service.create_notification`, never add email.
- **Reuse, do not duplicate.** Project-Head authorization is centralized in `app/core/authz.py` (`is_project_head`, `reviewable_project_ids`, `can_review_report`, `project_head_employee_id`) — every new check in this plan calls these, never re-implements them. The PM's leave UI (`LeaveManagementPanel`, `LeaveReviewPanel`, `AdminLeaveList`, `LeaveCancellationReviewPanel`) is reused unmodified in content, only re-parented for a Head.
- **No new "head" role and no new per-leave approver-id field.** Head-ness stays fully derived from `Project.head_employee_id`, exactly as it already works for Work Reports. The only new column is `leave_requests.routed_project_id` (the historical **project**, not a frozen head id) — see Task 1 and Task 2's module docstring for why.
- **Dynamic Head resolution.** The Head who may act on / gets notified about a routed request is always the project's **current** `head_employee_id`, looked up fresh at notify/list/approve time — never cached on the leave row. Only the *project* is historical (frozen at submission).
- **Backend enforces authorization; the frontend only hides buttons.** Every new/loosened check in Task 4 must independently reject an unauthorized caller even if the frontend is bypassed.
- **PM's existing behavior is fully preserved, unscoped.** A PM continues to see and may approve/reject every leave request exactly as today (see Task 4's design note) — Head access is purely additive, never a narrowing of PM's authority.
- **Employee's existing Leave page is untouched.** A plain employee (not PM, not a Head of any project) must see byte-for-byte the same `LeaveHistory` experience as before.

---

## Task 1: `routed_project_id` column, model, schema, and test fixtures

**Files:**
- Create: `backend/alembic/versions/0073_leave_routed_project.py`
- Modify: `backend/app/modules/leave/models.py`
- Modify: `backend/app/modules/leave/schemas.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_leave_routing.py` (new file — this task only adds the round-trip test; routing-logic tests are Task 2)

**Interfaces:**
- Produces: `LeaveRequest.routed_project_id: uuid.UUID | None` (FK `projects.id`, `ondelete="SET NULL"`, nullable, indexed `leave_routed_project_idx`); `LeaveRequestOut.routed_project_id: uuid.UUID | None`; `make_project(..., head_employee_id=None)` and `make_leave_request(..., routed_project_id=None)` test fixtures.

- [ ] **Step 1: Write the failing round-trip test**

```python
# backend/tests/test_leave_routing.py
"""Tests for leave-approval routing to Project Head (Phase 1).

`test_leave_routing.py` covers the resolver (Task 2) and this file's own
Task-1 smoke test that `routed_project_id` persists and serializes. Task 3/4
API-level behavior (notification target, scope, authorization) lives in
`test_leave_api.py` alongside the rest of the leave RBAC suite it extends.
"""
from datetime import date

from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType


def test_routed_project_id_persists(db, make_employee, make_user, make_project):
    u = make_user("emp@x.com")
    emp = make_employee(employee_code="E1", user_id=u.id)
    project = make_project(code="P-1")

    req = LeaveRequest(
        employee_id=emp.id,
        leave_type=LeaveType.casual,
        start_date=date.today(),
        end_date=date.today(),
        status=LeaveStatus.pending,
        routed_project_id=project.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    assert req.routed_project_id == project.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_routing.py -v`
Expected: FAIL — `TypeError: 'routed_project_id' is an invalid keyword argument for LeaveRequest` (column doesn't exist yet).

- [ ] **Step 3: Add the column to the model**

In `backend/app/modules/leave/models.py`, add the column right after `manager_comment` (before `created_by`):

```python
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The project the employee's PREVIOUS WORKING DAY's Daily Work Report shows
    # them on, resolved once at creation by leave/routing.py. This is the
    # historical PROJECT only — never a frozen head id. Who may review/is
    # notified is always the project's CURRENT head_employee_id, looked up
    # fresh via app.core.authz at read/notify/approve time, so a Head
    # reassignment after this request was filed is honoured (Phase 1 spec §15).
    # NULL means no single project could be determined - the request falls
    # back to the existing PM approval flow.
    routed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

And add the index alongside the existing three:

```python
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_order"),
        Index("leave_employee_idx", "employee_id", "start_date"),
        Index("leave_manager_idx", "manager_id", "status"),
        Index("leave_status_idx", "status"),
        Index("leave_routed_project_idx", "routed_project_id"),
    )
```

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0073_leave_routed_project.py
"""0073 leave routed project

Adds `routed_project_id` to `leave_requests` — Phase 1 of leave-approval
routing to Project Head. Nullable, SET NULL when the project is deleted.

This is the historical PROJECT the employee's previous working day's Daily
Work Report shows them on — resolved once at creation (leave/routing.py) and
never rewritten. It is NOT a frozen approver: whether a Head reviews this
request, and which Head, is always resolved from the project's CURRENT
head_employee_id at read/notify/approve time (app.core.authz), so a Head
reassignment after the request was filed is honoured. NULL means no single
project could be determined and the request falls back to the existing PM
approval flow, exactly as before this migration.

Revision ID: 0073_leave_routed_project
Revises: 0072_prod_status_activity
Create Date: 2026-08-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073_leave_routed_project"
down_revision: Union[str, None] = "0072_prod_status_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leave_requests", sa.Column(
        "routed_project_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index(
        "leave_routed_project_idx", "leave_requests", ["routed_project_id"],
    )


def downgrade() -> None:
    op.drop_index("leave_routed_project_idx", table_name="leave_requests")
    op.drop_column("leave_requests", "routed_project_id")
```

Confirm `down_revision` is exactly `"0072_prod_status_activity"` by re-reading the `revision` string at the top of `backend/alembic/versions/0072_prod_status_activity_label.py` before running — do not guess from the filename.

- [ ] **Step 5: Add the field to the response schema**

In `backend/app/modules/leave/schemas.py`, add to `LeaveRequestOut` (after `manager_comment`):

```python
    manager_comment: str | None = None
    routed_project_id: uuid.UUID | None = None
    created_at: datetime
```

- [ ] **Step 6: Extend the test fixtures**

In `backend/tests/conftest.py`, add `head_employee_id` to `make_project`:

```python
@pytest.fixture()
def make_project(db):
    def _make(
        *,
        code: str,
        name: str = "Test Project",
        client: str | None = None,
        status: ProjectStatus = ProjectStatus.planning,
        start_date=None,
        planned_completion_date=None,
        end_date=None,  # legacy alias
        head_employee_id=None,
    ) -> Project:
        project = Project(
            code=code,
            name=name,
            client=client,
            status=status,
            start_date=start_date,
            planned_completion_date=planned_completion_date or end_date,
            head_employee_id=head_employee_id,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    return _make
```

And `routed_project_id` to `make_leave_request`:

```python
@pytest.fixture()
def make_leave_request(db):
    def _make(
        *,
        employee_id,
        leave_type: LeaveType = LeaveType.casual,
        start_date,
        end_date,
        reason: str | None = "Test reason",
        status: LeaveStatus = LeaveStatus.pending,
        manager_id=None,
        routed_project_id=None,
        created_by=None,
    ) -> LeaveRequest:
        req = LeaveRequest(
            employee_id=employee_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status=status,
            manager_id=manager_id,
            routed_project_id=routed_project_id,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    return _make
```

- [ ] **Step 7: Run the migration and the test**

Run: `docker exec wms-backend-1 alembic upgrade head` then `docker exec wms-backend-1 pytest backend/tests/test_leave_routing.py backend/tests/test_leave_api.py -v`
Expected: PASS (the test DB is typically rebuilt from models by the test suite's own setup — if `test_leave_routing.py` still fails after the model change, check whether the test fixtures use a separate schema-creation path and run that instead of/in addition to `alembic upgrade head`; the migration must still exist and be correct either way).

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/0073_leave_routed_project.py backend/app/modules/leave/models.py backend/app/modules/leave/schemas.py backend/tests/conftest.py backend/tests/test_leave_routing.py
git commit -m "feat(leave): add routed_project_id column for Project-Head routing"
```

---

## Task 2: `resolve_routed_project` — the historical-project resolver

**Files:**
- Create: `backend/app/modules/leave/routing.py`
- Test: `backend/tests/test_leave_routing.py` (extend from Task 1)

**Interfaces:**
- Consumes: `app.modules.calendar.working_days.previous_working_day(db, reference: date, *, max_lookback_days: int = 30) -> date | None`; `app.modules.work_reports.models.DailyWorkReport` (fields: `id`, `employee_id`, `report_date`); `app.modules.work_reports.models.WorkReportTask` (fields: `report_id`, `project_id`).
- Produces: `resolve_routed_project(db: Session, employee_id: uuid.UUID, leave_date: date) -> uuid.UUID | None` — consumed by Task 3's `create_leave_request`.

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_leave_routing.py
from datetime import date, timedelta

from app.modules.leave import routing
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn


def _task(project_id, minutes=120):
    return WorkReportTaskIn(project_id=project_id, description="work", minutes_spent=minutes)


def _next_monday(from_date: date) -> date:
    return from_date + timedelta(days=(7 - from_date.weekday()) % 7 or 7)


def test_resolve_routed_project_single_project(
    db, make_user, make_employee, make_project, make_project_member,
):
    u = make_user("emp2@x.com")
    emp = make_employee(employee_code="E2", user_id=u.id)
    project = make_project(code="P-2")
    make_project_member(project_id=project.id, employee_id=emp.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)  # previous working day before a Monday

    wr_svc.create_work_report(db, u, WorkReportCreate(report_date=friday, tasks=[_task(project.id)]))

    resolved = routing.resolve_routed_project(db, emp.id, monday)
    assert resolved == project.id


def test_resolve_routed_project_skips_weekend(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Monday's leave routes off Friday's report - Sat/Sun are never checked,
    proving previous_working_day (not a naive `date - 1`) drives the lookup."""
    u = make_user("emp3@x.com")
    emp = make_employee(employee_code="E3", user_id=u.id)
    project = make_project(code="P-3")
    make_project_member(project_id=project.id, employee_id=emp.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(db, u, WorkReportCreate(report_date=friday, tasks=[_task(project.id)]))
    # A Saturday report must NOT be picked over Friday's - previous_working_day
    # never lands on a weekend, so create one and confirm it's ignored.
    other_project = make_project(code="P-3B")
    make_project_member(project_id=other_project.id, employee_id=emp.id)
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday + timedelta(days=1), tasks=[_task(other_project.id)])
    )

    resolved = routing.resolve_routed_project(db, emp.id, monday)
    assert resolved == project.id


def test_resolve_routed_project_no_report_falls_back(db, make_user, make_employee):
    u = make_user("emp4@x.com")
    emp = make_employee(employee_code="E4", user_id=u.id)
    monday = _next_monday(date.today())

    assert routing.resolve_routed_project(db, emp.id, monday) is None


def test_resolve_routed_project_no_tasks_falls_back(db, make_user, make_employee):
    """A no-activity day (leave/holiday/week-off) legitimately has zero task
    rows - that's a real state, not an error, and must fall back cleanly.
    `day_status` must be one of NO_ACTIVITY_DAY_STATUSES (e.g. week_off) or
    `create_work_report` itself rejects an empty-task report as invalid."""
    from app.modules.work_reports.models import DayStatus

    u = make_user("emp5@x.com")
    emp = make_employee(employee_code="E5", user_id=u.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, day_status=DayStatus.week_off, tasks=[])
    )

    assert routing.resolve_routed_project(db, emp.id, monday) is None


def test_resolve_routed_project_ambiguous_falls_back(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Two distinct projects on the same day - do not guess, fall back."""
    u = make_user("emp6@x.com")
    emp = make_employee(employee_code="E6", user_id=u.id)
    project_a = make_project(code="P-6A")
    project_b = make_project(code="P-6B")
    make_project_member(project_id=project_a.id, employee_id=emp.id)
    make_project_member(project_id=project_b.id, employee_id=emp.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, tasks=[_task(project_a.id), _task(project_b.id, 60)])
    )

    assert routing.resolve_routed_project(db, emp.id, monday) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_routing.py -v -k resolve_routed_project`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.leave.routing'`.

- [ ] **Step 3: Write the resolver**

```python
# backend/app/modules/leave/routing.py
"""Resolves which project (and therefore which Project Head) a new leave
request routes to, from the employee's PREVIOUS WORKING DAY's Daily Work
Report — Phase 1 of leave-approval routing to Project Head.

  leave start_date
        -> previous working day    (calendar.working_days.previous_working_day)
        -> that day's Daily Work Report (work_reports.models.DailyWorkReport)
        -> the DISTINCT project(s) logged on it (work_reports.models.WorkReportTask)
        -> exactly one project  -> route there
           zero, ambiguous (>1), or no report at all -> PM fallback (None)

This module resolves the PROJECT only, once, at submission time, and its
result is stored on `LeaveRequest.routed_project_id`. It never resolves a
Head: which Head (if any) currently owns that project is looked up
separately, at read/notify/approve time, via `app.core.authz` — so a Head
reassignment after this request was filed is always honoured (Phase 1
spec §15), while the historical project itself never changes.

A report's status (draft/submitted/granted) is deliberately NOT checked here:
Daily Work Reports have no approval gate (a submitted report is simply
locked from further edits), so a draft report is not less authoritative
about what the employee actually logged that day.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.calendar.working_days import previous_working_day
from app.modules.work_reports.models import DailyWorkReport, WorkReportTask


def resolve_routed_project(
    db: Session, employee_id: uuid.UUID, leave_date: date
) -> uuid.UUID | None:
    """The one project the employee logged on their previous working day
    before `leave_date`, or None if it can't be unambiguously determined
    (no working day found, no report, no tasks, or more than one project) —
    in every None case the caller falls back to the existing PM approval flow.
    """
    prev_day = previous_working_day(db, leave_date)
    if prev_day is None:
        return None

    report = db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == prev_day,
        )
    ).scalar_one_or_none()
    if report is None:
        return None

    project_ids = set(
        db.execute(
            select(WorkReportTask.project_id).where(
                WorkReportTask.report_id == report.id
            )
        ).scalars()
    )
    if len(project_ids) != 1:
        return None
    return next(iter(project_ids))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_routing.py -v`
Expected: PASS (6 tests: the Task 1 smoke test + the 5 above).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/leave/routing.py backend/tests/test_leave_routing.py
git commit -m "feat(leave): resolve routed project from previous working day's report"
```

---

## Task 3: Wire routing into creation + route the submission/cancellation notifications

**Files:**
- Modify: `backend/app/modules/leave/service.py`
- Test: `backend/tests/test_leave_api.py` (extend)

**Interfaces:**
- Consumes: `routing.resolve_routed_project` (Task 2); `app.core.authz.project_head_employee_id(db, project_id) -> uuid.UUID | None` (already exists).
- Produces: `_notify_routed_approver(db, employee, req, type_, title, message) -> None` — a new private helper other tasks do not need to call directly (Task 3 wires it into `create_leave_request`, `cancel_leave_request`, `request_leave_cancellation` only).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_leave_api.py`:

```python
def test_create_routes_to_project_head_and_notifies(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    hu = make_user("head1@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HEAD1", user_id=hu.id)
    project = make_project(code="RP-1", head_employee_id=head.id)

    eu = make_user("emp10@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E10", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    leave_date = date.today() + timedelta(days=7)
    prev_day = leave_date - timedelta(days=1)
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp10@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    note = db.query(Notification).filter(Notification.user_id == hu.id).one()
    assert note.type == "leave_submitted"
    assert note.target_url == f"/attendance?tab=leave&queue=pending&id={body['id']}"


def test_create_no_head_falls_back_to_manager_notification(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    """The previous day's project DOES resolve, but has no Head assigned -
    routed_project_id is still recorded, only the notification falls back."""
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    project = make_project(code="RP-2")  # no head_employee_id

    mu = make_user("mgr10@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR10", user_id=mu.id)
    eu = make_user("emp11@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E11", user_id=eu.id, manager_id=mgr.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    leave_date = date.today() + timedelta(days=7)
    prev_day = leave_date - timedelta(days=1)
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp11@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    note = db.query(Notification).filter(Notification.user_id == mu.id).one()
    assert note.type == "leave_submitted"
    assert note.target_url == f"/attendance?tab=leave&id={body['id']}"


def test_create_self_as_head_falls_back_to_manager_notification(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    """The employee IS the routed project's Head - notifying them about their
    own submission makes no sense, so this must fall back to their manager,
    same as the no-head case."""
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    mu = make_user("mgr11@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR11", user_id=mu.id)
    eu = make_user("emp12@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E12", user_id=eu.id, manager_id=mgr.id)
    project = make_project(code="RP-3", head_employee_id=emp.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    leave_date = date.today() + timedelta(days=7)
    prev_day = leave_date - timedelta(days=1)
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp12@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text

    assert db.query(Notification).filter(Notification.user_id == mu.id).count() == 1
    assert db.query(Notification).filter(Notification.user_id == eu.id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_api.py -v -k "routes_to_project_head or falls_back_to_manager"`
Expected: FAIL — `body["routed_project_id"]` is `None` (never set), and the Head never receives a notification (goes to no one / wrong recipient).

- [ ] **Step 3: Add the routing import and the routed-approver notify helper**

In `backend/app/modules/leave/service.py`, add to the imports (near the top, with the other `app.modules.leave.*` imports):

```python
from app.core import authz
from app.modules.leave import routing
```

Add the new helper right after `_notify_manager` (after line 260 in the current file, before `_notify_employee`):

```python
def _notify_routed_approver(db: Session, employee: Employee, req: LeaveRequest,
                            type_: str, title: str, message: str) -> None:
    """Notify whoever this request is routed to: the CURRENT Head of
    `req.routed_project_id` if one is assigned (and isn't the requester
    themself), else the employee's manager - the existing PM-fallback path,
    unchanged.

    The Head is resolved fresh here, never read off a value stored at
    submission time, so a Head reassignment after filing still notifies the
    right person (spec §15).
    """
    head_id = (
        authz.project_head_employee_id(db, req.routed_project_id)
        if req.routed_project_id is not None
        else None
    )
    if head_id is not None and head_id != employee.id:
        head = db.get(Employee, head_id)
        if head is not None and head.user_id is not None:
            _push(db, head.user_id, type_, title, message, req.id,
                  f"/attendance?tab=leave&queue=pending&id={req.id}")
            return
    _notify_manager(db, employee, type_, title, message, req.id,
                    f"/attendance?tab=leave&id={req.id}")
```

- [ ] **Step 4: Set `routed_project_id` at creation and route its notification**

In `create_leave_request`, add `routed_project_id=...` to the `LeaveRequest(...)` construction:

```python
    req = LeaveRequest(
        employee_id=me.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status=LeaveStatus.pending,
        routed_project_id=routing.resolve_routed_project(db, me.id, data.start_date),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    _notify_routed_approver(
        db, me, req, "leave_submitted",
        f"{me.full_name} submitted a leave request",
        f"{me.full_name} requested {data.leave_type.value} leave from {data.start_date} to {data.end_date}.",
    )
    return req
```

(This replaces the existing `_notify_manager(db, me, "leave_submitted", ..., req.id, f"/attendance?tab=leave&id={req.id}")` call — delete it, the new `_notify_routed_approver` call takes over both the routing and the fallback.)

- [ ] **Step 5: Route the cancellation-related notifications the same way**

These two are the notifications that tell someone a **decision is needed** or **has happened on their queue** — they must reach the same person Task 4 will authorize to act, not always the manager. In `cancel_leave_request`, replace:

```python
    _notify_manager(
        db, me, "leave_cancelled",
        f"{me.full_name} cancelled a leave request",
        f"{me.full_name} cancelled their leave request ({req.start_date} to {req.end_date}).",
        req.id,
        f"/attendance?tab=leave&id={req.id}",
    )
```
with:
```python
    _notify_routed_approver(
        db, me, req, "leave_cancelled",
        f"{me.full_name} cancelled a leave request",
        f"{me.full_name} cancelled their leave request ({req.start_date} to {req.end_date}).",
    )
```

And in `request_leave_cancellation`, replace:

```python
    _notify_manager(
        db, me, "leave_cancellation_requested",
        f"{me.full_name} requested leave cancellation",
        f"{me.employee_code} - {me.full_name} requested cancellation of approved "
        f"leave for {_period(req)}.",
        req.id,
        f"/attendance?tab=leave&queue=cancellation&id={req.id}",
    )
```
with:
```python
    _notify_routed_approver(
        db, me, req, "leave_cancellation_requested",
        f"{me.full_name} requested leave cancellation",
        f"{me.employee_code} - {me.full_name} requested cancellation of approved "
        f"leave for {_period(req)}.",
    )
```

Note the `target_url` for these two keeps the `_notify_routed_approver`-computed URL (`/attendance?tab=leave&queue=pending&id=...` for a Head, or the old `/attendance?tab=leave&id=...` for the PM fallback) rather than the old cancellation-specific `queue=cancellation` URL — that's an acceptable, deliberately small simplification for Phase 1 (the notification still deep-links to the request; Task 4 does not scope the Head's *cancellation* queue tab, only Pending/All, so a `queue=cancellation` link would 404 into the wrong tab for a Head anyway). Do not change `approve_leave_cancellation`'s or `reject_leave_cancellation`'s `_notify_employee(...)` calls — those notify the requesting employee about an outcome, not an approver about a pending decision, and are unaffected by routing.

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_api.py backend/tests/test_leave_routing.py backend/tests/test_leave_cancellation.py backend/tests/test_leave_phase10.py -v`
Expected: PASS — all new tests plus every pre-existing leave test (regression check).

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/leave/service.py backend/tests/test_leave_api.py
git commit -m "feat(leave): route submission/cancellation notifications to the current Project Head"
```

---

## Task 4: Authorization — a Head may review requests routed to their project

**Files:**
- Modify: `backend/app/modules/leave/service.py`
- Modify: `backend/app/modules/leave/router.py`
- Test: `backend/tests/test_leave_api.py` (extend)

**Interfaces:**
- Consumes: `authz.reviewable_project_ids(db, actor) -> set[uuid.UUID]`, `authz.can_review_report(db, actor, project_ids: set[uuid.UUID]) -> bool` (both already exist, unchanged).
- Produces: widened `_apply_scope`, `_assert_can_read`, `_assert_can_review` in `leave/service.py` — consumed by every existing list/get/approve/reject/cancellation function unchanged (no call-site signature changes).

**Design note (read before editing):** PM's authority stays exactly as it is today — fully unscoped, sees and may act on every request. This is deliberate: the spec requires "PM retains their existing approval authority" (§16) and nothing in the spec asks for narrowing PM's view when a Head exists, so Head access here is purely *additive* — a Head sees/acts on requests routed to their project(s) *in addition to* their own, and a PM is completely unaffected. If a request is routed to a Head, both that Head and any PM may act on it; the existing `SELECT ... FOR UPDATE` lock-then-check pattern (`_fetch_locked`) already resolves that race to exactly one winner, so no new locking is needed.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_leave_api.py`:

```python
def _fund_and_login(login, email):
    return login(email)


def test_head_sees_only_own_routed_requests(
    client, db, make_user, make_employee, make_project, login,
):
    head_a_u = make_user("heada@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HA", user_id=head_a_u.id)
    head_b_u = make_user("headb@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HB", user_id=head_b_u.id)
    project_a = make_project(code="SC-A", head_employee_id=head_a.id)
    project_b = make_project(code="SC-B", head_employee_id=head_b.id)

    emp_a_u = make_user("empa@x.com", role=UserRole.employee)
    emp_a = make_employee(employee_code="EA", user_id=emp_a_u.id)
    emp_b_u = make_user("empb@x.com", role=UserRole.employee)
    emp_b = make_employee(employee_code="EB", user_id=emp_b_u.id)
    make_employee(employee_code="EC", user_id=make_user("empc@x.com").id)  # unrelated, no routing

    req_a = _make_leave(db, emp_a.id, routed_project_id=project_a.id)
    req_b = _make_leave(db, emp_b.id, routed_project_id=project_b.id)

    h = login("heada@x.com")
    res = client.get("/api/v1/leave-requests", headers=h, params={"status": "pending"}).json()
    ids = {row["id"] for row in res["items"]}
    assert str(req_a.id) in ids
    assert str(req_b.id) not in ids


def test_head_can_approve_own_routed_request(
    client, db, make_user, make_employee, make_project, login,
):
    head_u = make_user("headc@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HC", user_id=head_u.id)
    project = make_project(code="SC-C", head_employee_id=head.id)

    emp_u = make_user("empd@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="ED", user_id=emp_u.id)
    _fund(db, emp.id)

    req = _make_leave(db, emp.id, routed_project_id=project.id)

    h = login("headc@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_head_cannot_approve_other_heads_request(
    client, db, make_user, make_employee, make_project, login,
):
    head_a_u = make_user("heade@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HE", user_id=head_a_u.id)
    make_project(code="SC-D", head_employee_id=head_a.id)
    head_b_u = make_user("headf@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HF", user_id=head_b_u.id)
    project_b = make_project(code="SC-E", head_employee_id=head_b.id)

    emp_u = make_user("empe@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EF", user_id=emp_u.id)
    req = _make_leave(db, emp.id, routed_project_id=project_b.id)

    h = login("heade@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_plain_employee_cannot_approve_anyone(
    client, db, make_user, make_employee, make_project, login,
):
    project = make_project(code="SC-F")  # no head
    emp_u = make_user("empf@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EG", user_id=emp_u.id)
    other_u = make_user("empg@x.com", role=UserRole.employee)
    other = make_employee(employee_code="EH", user_id=other_u.id)
    req = _make_leave(db, other.id, routed_project_id=project.id)

    h = login("empf@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_head_cannot_approve_own_leave_even_if_self_routed(
    client, db, make_user, make_employee, make_project, login,
):
    head_u = make_user("headg@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HG", user_id=head_u.id)
    project = make_project(code="SC-G", head_employee_id=head.id)
    req = _make_leave(db, head.id, routed_project_id=project.id)

    h = login("headg@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_reassigned_head_takes_over_review_authority(
    client, db, make_user, make_employee, make_project, login,
):
    """Spec §15: the PROJECT on the leave row is historical and frozen, but
    WHO may review it is always the project's CURRENT head_employee_id - a
    reassignment after the request was filed must be honoured immediately,
    with no change to the leave row itself."""
    head_a_u = make_user("headh@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HH", user_id=head_a_u.id)
    head_b_u = make_user("headi@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HI", user_id=head_b_u.id)
    project = make_project(code="SC-H", head_employee_id=head_a.id)

    emp_u = make_user("empi@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EI", user_id=emp_u.id)
    _fund(db, emp.id)  # casual leave deducts balance - approval needs it funded
    req = _make_leave(db, emp.id, routed_project_id=project.id)

    # Reassign the project's Head from A to B - simulates the PM's existing
    # `PUT /projects/{id}/head` action; nothing on the leave row changes.
    project.head_employee_id = head_b.id
    db.add(project)
    db.commit()

    h_a = login("headh@x.com")
    res_a = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h_a, json={})
    assert res_a.status_code == 403, res_a.text  # Head A lost authority

    h_b = login("headi@x.com")
    res_b = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h_b, json={})
    assert res_b.status_code == 200, res_b.text  # Head B has it now
```

Add this small local helper near the top of `test_leave_api.py` (below `_fund`/`_payload`), since several tests above need a pending request built directly with a `routed_project_id` rather than through the create endpoint (which would need a real previous-day report — Task 3 already covers that path end-to-end):

```python
def _make_leave(db, employee_id, *, routed_project_id=None, start=None, end=None):
    req = LeaveRequest(
        employee_id=employee_id,
        leave_type=LeaveType.casual,
        start_date=start or (date.today() + timedelta(days=7)),
        end_date=end or (date.today() + timedelta(days=7)),
        reason="Test",
        status=LeaveStatus.pending,
        routed_project_id=routed_project_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req
```

This needs `from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType` — `LeaveStatus`/`LeaveType` are already imported at the top of the file; add `LeaveRequest` to that same import line.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_api.py -v -k "head_sees_only or head_can_approve or head_cannot or plain_employee_cannot or reassigned_head"`
Expected: FAIL — the router still 403s a non-PM before the service is even reached (`require_reviewer`), and `_apply_scope`/`_assert_can_review` don't know about Heads yet.

- [ ] **Step 3: Widen `_apply_scope`**

In `backend/app/modules/leave/service.py`, add `or_` to the existing `from sqlalchemy import func, select` import (`from sqlalchemy import func, or_, select`), then replace `_apply_scope`:

```python
def _apply_scope(db: Session, actor: User, stmt):
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    head_project_ids = authz.reviewable_project_ids(db, actor)
    if head_project_ids:
        return (
            stmt.where(
                or_(
                    LeaveRequest.employee_id == me.id,
                    LeaveRequest.routed_project_id.in_(head_project_ids),
                )
            ),
            True,
        )
    return stmt.where(LeaveRequest.employee_id == me.id), True
```

- [ ] **Step 4: Widen `_assert_can_read`**

```python
def _assert_can_read(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role == UserRole.project_manager:
        return
    if req.routed_project_id is not None and authz.can_review_report(
        db, actor, {req.routed_project_id}
    ):
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if req.employee_id == me.id:
        return
    raise AppError("forbidden", "You can only view your own leave requests.", 403)
```

- [ ] **Step 5: Widen `_assert_can_review`**

```python
def _assert_can_review(db: Session, actor: User, req: LeaveRequest | None = None) -> None:
    """Who may rule on a leave request - enforced here, in the backend, on every
    decision path. The frontend hides the buttons; this is what actually stops it.

    PM (any request) or the CURRENT Head of the request's routed project may
    review. `authz.can_review_report` already encodes exactly that rule (it's
    the same helper Work Reports uses) so this stays a one-line delegation
    rather than a second copy of the PM-or-Head check.

    NOBODY REVIEWS THEIR OWN LEAVE, including a project manager or a Head:
    project managers and Heads are employees too and file their own requests,
    so without the second check either could approve their own leave and grant
    themselves the balance. `req` is therefore passed on every decision path -
    approve, reject, and both cancellation decisions.
    """
    project_ids = {req.routed_project_id} if (req is not None and req.routed_project_id is not None) else set()
    if not authz.can_review_report(db, actor, project_ids):
        raise AppError(
            "forbidden",
            "Only a project manager or this request's assigned Project Head can review it.",
            403,
        )
    if req is None:
        return
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own leave request - another reviewer has to decide it.",
            403,
        )
```

- [ ] **Step 6: Loosen the router-level gate on the four decision endpoints**

In `backend/app/modules/leave/router.py`, the `require_reviewer = require_role("project_manager")` dependency currently gates `/approve`, `/reject`, `/approve-cancellation`, `/reject-cancellation` **before** the request ever reaches `_assert_can_review` — a Head (role `"employee"`) would be rejected right there regardless of Task 4's service changes. Change those four endpoints' dependency from `Depends(require_reviewer)` to `Depends(get_current_user)`, matching every other non-PM-only endpoint in this router; `_assert_can_review` (Step 5) is what actually enforces "PM or the routed project's Head" now, exactly as it already enforces "not your own request" today.

```python
@router.post("/{req_id}/approve-cancellation", response_model=LeaveRequestOut)
def approve_leave_cancellation(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    ...

@router.post("/{req_id}/reject-cancellation", response_model=LeaveRequestOut)
def reject_leave_cancellation(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    ...

@router.post("/{req_id}/approve", response_model=LeaveRequestOut)
def approve_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    ...

@router.post("/{req_id}/reject", response_model=LeaveRequestOut)
def reject_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    ...
```

Do **not** touch `deliverable_impact` or `attendance_summary` — both stay `Depends(require_reviewer)` (PM-only decision-support views, out of Phase 1 scope for Heads per this plan's Global Constraints).

- [ ] **Step 7: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest backend/tests/test_leave_api.py backend/tests/test_leave_cancellation.py backend/tests/test_leave_phase10.py backend/tests/test_leave_ledger.py backend/tests/test_leave_biometric_block.py backend/tests/test_leave_monthly_notice.py -v`
Expected: PASS — the 5 new tests, and every pre-existing leave test including `test_project_manager_sees_all_leave_requests` / `test_admin_sees_all` (PM regression).

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/leave/service.py backend/app/modules/leave/router.py backend/tests/test_leave_api.py
git commit -m "feat(leave): authorize Project Head to review requests routed to their project"
```

---

## Task 5: Frontend — Head gets the same Pending/All Leave UI as PM, employee UI intact

**Files:**
- Modify: `frontend/src/features/leave/hooks.ts`
- Modify: `frontend/src/features/permissions/hooks.ts`
- Modify: `frontend/src/features/leave/components/leave-management-panel.tsx`
- Modify: `frontend/src/features/leave/components/leave-tab.tsx`
- Modify: `frontend/src/features/leave/types.ts`
- Create: `frontend/src/features/leave/components/head-leave-tab.tsx`

**Interfaces:**
- Consumes: `useReportScope(options?: { enabled?: boolean })` from `@/features/work-reports/hooks` (already exists — returns `{ is_project_head, is_activity_lead, projects }`); `useUrlState(key, fallback)` from `@/lib/use-url-state`; `Tabs` from `@/components/ui/tabs`.
- Produces: `HeadLeaveTab({ employeeId }: { employeeId?: string })`; `LeaveManagementPanel({ employeeId, showPermissionQueue = true })` (existing signature widened, PM call sites unaffected by the default).

- [ ] **Step 1: Add `options.enabled` support to `useLeaveList` and `usePermissionList`**

These are called unconditionally today; `HeadLeaveTab`/`LeaveManagementPanel` need to skip the permission-queue count query when hidden for a Head. In `frontend/src/features/leave/hooks.ts`:

```typescript
export function useLeaveList(params: LeaveListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: leaveKeys.list(params),
    queryFn: () => leaveApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}
```

In `frontend/src/features/permissions/hooks.ts`:

```typescript
export function usePermissionList(params: PermissionListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: permissionKeys.list(params),
    queryFn: () => permissionApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}
```

Both changes are backward compatible (new second param, optional, defaults to the previous always-on behavior) — every existing call site (including `project-manager-dashboard.tsx`) keeps working unchanged.

- [ ] **Step 2: Add `showPermissionQueue` to `LeaveManagementPanel`**

In `frontend/src/features/leave/components/leave-management-panel.tsx`:

```tsx
interface Props {
  employeeId?: string;
  /** A Project Head gets Pending/Cancellation/All (leave only) - Permission
   *  Requests is an unrelated, PM-only attendance-permission domain and stays
   *  hidden for a Head, per Phase 1's leave-only scope. Defaults to true so
   *  every existing PM call site is unaffected. */
  showPermissionQueue?: boolean;
}

export function LeaveManagementPanel({ employeeId, showPermissionQueue = true }: Props) {
  const [rawQueue, setQueue] = useUrlState("queue", "pending");
  const queue = resolveLeaveQueue(rawQueue);

  const pendingCount =
    useLeaveList({ status: "pending", limit: 1, offset: 0 }).data?.total ?? 0;
  const cancellationCount =
    useLeaveList({ status: "cancellation_requested", limit: 1, offset: 0 }).data?.total ?? 0;
  const permissionCount =
    usePermissionList(
      { status: "pending", limit: 1, offset: 0 },
      { enabled: showPermissionQueue },
    ).data?.total ?? 0;

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          {
            value: "pending",
            label: "Pending requests",
            count: pendingCount || undefined,
            countVariant: "warning",
          },
          {
            value: "cancellation",
            label: "Cancellation requests",
            count: cancellationCount || undefined,
            countVariant: "info",
          },
          ...(showPermissionQueue
            ? [{
                value: "permission",
                label: "Permission requests",
                count: permissionCount || undefined,
                countVariant: "warning" as const,
              }]
            : []),
          { value: "all", label: "All leave" },
        ]}
        value={queue}
        onChange={setQueue}
      />

      {queue === "pending" && <LeaveReviewPanel employeeId={employeeId} />}
      {queue === "cancellation" && <LeaveCancellationReviewPanel />}
      {queue === "permission" && showPermissionQueue && <PermissionReviewPanel />}
      {queue === "all" && <AdminLeaveList />}
    </div>
  );
}
```

- [ ] **Step 3: Create `HeadLeaveTab`**

```tsx
// frontend/src/features/leave/components/head-leave-tab.tsx
"use client";

import { useSearchParams } from "next/navigation";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

interface Props {
  employeeId?: string;
}

/** A Project Head keeps their own employee Leave history AND gets the same
 *  approval UI a PM has (Pending/Cancellation/All), scoped server-side to the
 *  projects they Head via `authz.reviewable_project_ids` - no client-side
 *  filtering needed, the same `useLeaveList` calls PM's panel already makes
 *  come back pre-scoped for a Head actor.
 *
 *  Defaults to "My leave" so a Head landing on the tab cold sees exactly what
 *  a plain employee always saw; the homepage shortcut
 *  (?tab=leave&queue=pending) forces "Team approvals" straight open by
 *  checking for a `queue` param before applying that default. */
export function HeadLeaveTab({ employeeId }: Props) {
  const searchParams = useSearchParams();
  const hasQueueParam = searchParams.get("queue") !== null;
  const [view, setView] = useUrlState("view", hasQueueParam ? "team" : "my");

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          { value: "my", label: "My leave" },
          { value: "team", label: "Team approvals" },
        ]}
        value={view}
        onChange={setView}
      />
      {view === "my" && <LeaveHistory employeeId={employeeId} />}
      {view === "team" && (
        <LeaveManagementPanel employeeId={employeeId} showPermissionQueue={false} />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Route a Head to it from `LeaveTab`**

```tsx
// frontend/src/features/leave/components/leave-tab.tsx
"use client";

import { useAuth } from "@/features/auth/auth-provider";
import { useReportScope } from "@/features/work-reports/hooks";

import { HeadLeaveTab } from "./head-leave-tab";
import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

/** Role-aware Leave tab content embedded inside the Attendance page.
 *
 *  Employees see their own leave history. Project managers get the queue
 *  container. A Project Head (role stays "employee"; Head-ness is per-project,
 *  derived server-side from Project.head_employee_id - see
 *  `app.core.authz.reviewable_project_ids`, the same fact Work Reports already
 *  surfaces via `useReportScope`) gets BOTH their own history and a
 *  PM-equivalent approval view, via `HeadLeaveTab`.
 *
 *  PERMISSION HISTORY IS NOT HERE. It moved to /attendance/permission (Phase
 *  11A) ... */
export function LeaveTab() {
  const { role, employeeId } = useAuth();
  const { data: scope } = useReportScope({ enabled: role !== "project_manager" });
  const isProjectHead = role !== "project_manager" && scope?.is_project_head === true;

  if (role === "project_manager") {
    return <LeaveManagementPanel employeeId={employeeId ?? undefined} />;
  }

  if (isProjectHead) {
    return <HeadLeaveTab employeeId={employeeId ?? undefined} />;
  }

  return <LeaveHistory employeeId={employeeId ?? undefined} />;
}
```

Keep the rest of the original file's doc-comment content (the "PERMISSION HISTORY IS NOT HERE" paragraph) — only the imports, the new `scope`/`isProjectHead` lines, and the new `if` branch are additions.

- [ ] **Step 5: Add `routed_project_id` to the frontend `LeaveRequest` type**

In `frontend/src/features/leave/types.ts`, for schema accuracy with the backend response (Task 1) — not surfaced in any UI in Phase 1:

```typescript
export interface LeaveRequest {
  id: string;
  employee_id: string;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: LeaveStatus;
  manager_id: string | null;
  manager_comment: string | null;
  routed_project_id: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 6: Typecheck and manually verify in the browser**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

Manual check (dev server): as a plain employee, `/attendance?tab=leave` still shows only `LeaveHistory`. As the PM, it's still `LeaveManagementPanel` with all four tabs including Permission requests. As an employee who is `head_employee_id` on some project (seed one via the API or DB), `/attendance?tab=leave` shows the "My leave / Team approvals" tabs, and Team approvals has no "Permission requests" tab.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/leave/hooks.ts frontend/src/features/permissions/hooks.ts \
        frontend/src/features/leave/components/leave-management-panel.tsx \
        frontend/src/features/leave/components/leave-tab.tsx \
        frontend/src/features/leave/components/head-leave-tab.tsx \
        frontend/src/features/leave/types.ts
git commit -m "feat(leave): give Project Head the PM's Pending/All Leave UI alongside their own"
```

---

## Task 6: Frontend — homepage shortcut for a Project Head's pending leave

**Files:**
- Modify: `frontend/src/features/dashboard/employee-dashboard.tsx`

**Interfaces:**
- Consumes: `useReportScope` (`@/features/work-reports/hooks`), `useLeaveList` (`@/features/leave/hooks`, Task 5's `options.enabled`), `Badge` (`@/components/ui/badge`).

**Design note:** A Project Head keeps `role === "employee"`, so `DashboardView` (`isManagerial(role) ? <ProjectManagerDashboard/> : <EmployeeDashboard/>`) still routes them to `EmployeeDashboard` — the shortcut has to live there, gated on `is_project_head`, exactly mirroring how `ProjectManagerDashboard` already gates its own "Pending leave requests" card on a plain `useLeaveList({status:"pending"})` count.

- [ ] **Step 1: Add the scope/count queries and the conditional card**

In `frontend/src/features/dashboard/employee-dashboard.tsx`, add imports:

```tsx
import { CalendarOff, FileText, Plus } from "lucide-react";
// ^ CalendarOff already imported; add nothing new to this line if it's already there —
//   just confirm it, since the new button reuses the same icon as the existing
//   "Leave request" quick action.

import { Badge } from "@/components/ui/badge";
import { useLeaveList } from "@/features/leave/hooks";
import { useReportScope } from "@/features/work-reports/hooks";
```

Inside `EmployeeDashboard()`, after the existing `const { user, employee, employeeId } = useAuth();`:

```tsx
  const { data: scope } = useReportScope();
  const isProjectHead = scope?.is_project_head === true;
  const pendingLeave = useLeaveList(
    { status: "pending", limit: 1, offset: 0 },
    { enabled: isProjectHead },
  );
  const pendingLeaveCount = pendingLeave.data?.total ?? 0;
```

(`useReportScope()` is called unconditionally here — unlike `work-reports-view.tsx`, which skips it for managers, `EmployeeDashboard` by construction only ever renders for non-managerial roles, so there's no PM case to guard against.)

In the "Quick actions" card, add the shortcut right before the existing "Leave request" button, only when `isProjectHead`:

```tsx
              {isProjectHead && (
                <Button asChild className="justify-start" variant="secondary">
                  <Link href="/attendance?tab=leave&queue=pending">
                    <CalendarOff className="h-4 w-4" /> Pending leave requests
                    {pendingLeaveCount > 0 && (
                      <Badge variant="warning" className="ml-auto">
                        {pendingLeaveCount}
                      </Badge>
                    )}
                  </Link>
                </Button>
              )}
              <Button asChild className="justify-start" variant="secondary">
                <Link href="/attendance?leave=request"><CalendarOff className="h-4 w-4" /> Leave request</Link>
              </Button>
```

- [ ] **Step 2: Typecheck and manually verify**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

Manual check: as a plain employee (not a Head of anything), the dashboard's Quick actions card shows no "Pending leave requests" entry, unchanged from before. As an employee who is `head_employee_id` on some project with at least one pending routed request, the card shows "Pending leave requests" with a warning badge, and clicking it lands on `/attendance?tab=leave&queue=pending` with "Team approvals" already selected (Task 5, Step 3's `hasQueueParam` check).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/dashboard/employee-dashboard.tsx
git commit -m "feat(dashboard): add Pending leave requests shortcut for Project Heads"
```

---

## Task 7: End-to-end verification

No new files — this task runs the full suite, re-derives the scenarios from the Phase 1 spec against the real app, and reviews the diff before calling Phase 1 done. Do not skip this task; do not fold it into Task 6's commit.

- [ ] **Step 1: Full backend suite**

Run: `docker exec wms-backend-1 pytest -v`
Expected: PASS. Compare failure count against the known pre-existing-failures baseline (see the `running-tests` memory) — investigate anything new.

- [ ] **Step 2: Full frontend typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Manually walk every scenario from the Phase 1 spec's §18**

Using the running app (seed data via the API/admin UI as needed):

- **Scenario A** — Employee's previous working day report has Project A, Project A has Head A → the request appears in Head A's Pending Requests; Head A can approve and reject it (test both, on two separate requests).
- **Scenario B** — Employee's previous working day report has Project B, Project B has no Head → the request appears in the PM's Pending Requests exactly as before; PM approves it normally.
- **Scenario C** — Employee's previous working day was on Project A (with Head A), but the employee's *current* project assignment/membership is Project B → confirm the request still routes to Head A, not to whoever heads Project B.
- **Scenario D** — Employee A → Project A → Head A, Employee B → Project B → Head B, both submit leave → Head A sees only A's request, Head B sees only B's; neither sees the other's.
- **Scenario E** — Take a user who is a plain employee, assign them as `head_employee_id` on a project (PM does this via the existing project-head-assignment UI), confirm they now see both "My leave" and "Team approvals" on the same Leave tab, and their own leave-request flow is unaffected.
- **Scenario F** — As a Head with ≥1 pending routed request, confirm the homepage shortcut count matches, and clicking it opens Team approvals → Pending requests.
- **Scenario G** — As Head B, attempt `POST /leave-requests/{head_a_scoped_request_id}/approve` directly (e.g. via curl/Postman with Head B's token) → confirm `403`, not a UI-only block.

- [ ] **Step 4: Review the full diff for unintended changes**

Run: `git diff main...HEAD --stat` then `git diff main...HEAD`
Expected: Only the files listed across Tasks 1–6 are touched; no unrelated formatting/refactor changes crept in (per this plan's Global Constraints — no redesign, no unrelated cleanup).

- [ ] **Step 5: Report Phase 1 completion**

Summarize for the user, per the spec's "Definition of Done" reporting requirements: files changed, the one DB migration, API/backend changes (routing resolver, widened scope/authorization, loosened router dependency on 4 endpoints), frontend changes (HeadLeaveTab, dashboard shortcut, two hook signature widenings), notification changes (routed-approver notify helper), permission/authorization changes (per-project Head review via existing `authz` helpers, PM unchanged), tests run and their results, manual scenarios verified (A–G), and any unresolved edge cases (e.g., Head's Cancellation-requests queue is included per Task 5 Step 2 but this plan did not add a dedicated test for a Head approving a *cancellation* — flag this as a follow-up if the user wants full parity there, since Task 4's `_assert_can_review` already authorizes it identically to approve/reject, only the explicit test is missing).

Do not commit Task 7 itself — there is nothing to commit; if Step 3 or Step 4 surfaces a problem, fix it, add/adjust a test if the gap was in Tasks 1–6, and commit that fix under the task it belongs to.
