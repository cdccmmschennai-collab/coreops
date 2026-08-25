# Lump-sum Activity Continuation Approval (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a lump-sum (NON_QUANTITATIVE, i.e. `TASK_STATUS_ONLY`/legacy `TASK_BASED`) activity's allowed duration expires while incomplete, block the employee from continuing it until the current Project Head (or, with no Head, the employee's line manager) approves a continuation request — enforced server-side, with in-app notifications and a Head Attendance review UI.

**Architecture:** Reuse the existing feature-flagged `WorkItem` continuation engine (`app.modules.work_reports.work_items`) unchanged in its create/link mechanics; add one new gate inside `resolve_task_work_item`'s LINK path that blocks a new continuation entry on an overdue lump-sum item unless an approved `ContinuationRequest` exists for that `work_item_id`. `ContinuationRequest` is a new, dedicated table (its own module, mirroring `activity_requests`' thin request/approval shape) — never reusing `leave_requests` or `activity_requests`. Head/PM authorization reuses `app.core.authz` exactly as the Leave workflow does (current `Project.head_employee_id`, resolved fresh at read/notify/approve time — never frozen); PM-fallback reuses `Employee.manager_id`, matching Leave's `_notify_manager` exactly. `WorkItem.due_date` switches from calendar-day to working-day math (new `add_working_days` helper). Notifications reuse `app.modules.notifications.service.create_notification`. Frontend adds a Head-only "Lump-sum Activity Requests" tab to the existing `/attendance` page (cloning the Leave tab's table/badge/inline-approve-reject patterns) and an employee-facing "Continuation approval required" card inside the existing work-report form's "Open tasks" section.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (backend), Next.js + React Query + react-hook-form (frontend), pytest (backend tests), openapi-typescript for generated types.

**Spec:** This plan implements the Phase 2 spec given directly in conversation (no separate spec file) plus the 20 locked decisions and UI requirements from the user's approval message. Sibling reference: `docs/superpowers/plans/2026-08-23-leave-approval-routing-to-project-head.md` (the Leave-to-Head workflow this plan patterns itself after and must not modify).

## Global Constraints

- Do NOT modify the leave workflow (`app/modules/leave/*`, `frontend/src/features/leave/*`) except to leave it untouched and passing its existing tests.
- Do NOT implement email/SMTP anywhere. In-app notifications only.
- Do NOT create more than one Alembic migration for this phase (`0074_continuation_requests.py`).
- Do NOT introduce a new benchmark type or rename the existing `TASK_STATUS_ONLY`/`TASK_BASED`/`TASK_WITH_QUANTITY` enum values.
- Reuse `app.core.authz` for all Project Head / PM authorization — no new authorization helpers.
- Reuse `app.modules.notifications.service.create_notification` for every notification — no new notification infrastructure.
- `TASK_WITH_QUANTITY` continuation must be provably unaffected — every new gate is keyed off `is_lumpsum_unit_row(benchmark_type, relevant_count_field)` (existing helper in `activity_master/models.py`), never off `TASK_BENCHMARK_TYPES` membership alone.
- PM-fallback (no Project Head) routes to `Employee.manager_id`, matching `leave/service.py::_notify_manager` — not the `project_managers` assignment table.
- Self-approval/self-review is forbidden for both PM and Head reviewers, mirroring `leave/service.py::_assert_can_review`.
- `TASK_CONTINUATION_ENABLED` becomes `True` by default (backend `Settings` class + `.env.example`) as part of this phase.
- Run backend tests via `docker exec wms-backend-1 pytest`, frontend typecheck via `docker exec wms-frontend-1 npm run typecheck` (per project convention — compose env files are absent, so tests must run through the containers, not directly on the host).

## File Structure

**Backend — new module** `backend/app/modules/continuation_requests/`:
- `models.py` — `ContinuationRequest` ORM model + `ContinuationRequestStatus` enum.
- `schemas.py` — `ContinuationRequestCreate`, `ContinuationReviewBody`, `ContinuationRequestOut`, `ContinuationRequestPage`.
- `service.py` — create/list/get/approve/reject + `has_approved_continuation` + `latest_requests_by_work_item` (consumed by `work_items.py`) + notification wiring.
- `router.py` — 6 endpoints under `/continuation-requests`.

**Backend — modified:**
- `backend/alembic/versions/0074_continuation_requests.py` — new table + indexes.
- `backend/app/core/config.py` — flip `TASK_CONTINUATION_ENABLED` default to `True`.
- `backend/.env.example` — document `TASK_CONTINUATION_ENABLED=true`.
- `backend/app/modules/calendar/working_days.py` — add `next_working_day` + `add_working_days`.
- `backend/app/modules/work_reports/work_items.py` — `compute_due_date` takes `db` and computes working days; new approval gate in `resolve_task_work_item`; `get_open_work_items` gains continuation-approval fields.
- `backend/app/modules/work_reports/service.py` — `_validate_tasks` snapshot gains `is_lumpsum_task`; `compute_due_date` call sites pass `db`.
- `backend/app/modules/work_reports/schemas.py` — `OpenTaskOut` gains 4 fields.
- `backend/app/main.py` — register the new router.
- `backend/tests/test_task_continuation.py` — due-date tests updated for working-day math; new `flag_off` fixture for the one test that must stay off.

**Backend — new tests:**
- `backend/tests/test_working_days_forward.py` — `next_working_day` / `add_working_days`.
- `backend/tests/test_continuation_requests.py` — the full Phase 2 test matrix.

**Frontend — new module** `frontend/src/features/continuation-requests/`:
- `types.ts`, `api.ts`, `keys.ts`, `hooks.ts`
- `components/continuation-status-badge.tsx`
- `components/continuation-review-panel.tsx` (Pending Requests table + inline approve/reject)
- `components/all-continuation-requests-list.tsx` (All Requests history)
- `components/continuation-management-panel.tsx` (Pending/All inner tabs)
- `components/continuation-detail.tsx` (read-only detail page content)
- `components/continuation-approval-card.tsx` (employee-facing card, consumed by work-reports)

**Frontend — modified:**
- `frontend/src/features/attendance/tabs.ts` — new `TabKey` + gated tab entry.
- `frontend/src/features/attendance/components/attendance-view.tsx` — render branch + Head-scope resolution.
- `frontend/src/features/dashboard/employee-dashboard.tsx` — new shortcut.
- `frontend/src/features/notifications/types.ts` + `components/notification-item.tsx` — 3 new notification types.
- `frontend/src/features/work-reports/types.ts` — `OpenTask` type already derives from generated `OpenTaskOut` (no manual edit — regenerated).
- `frontend/src/features/work-reports/components/work-report-form.tsx` — branch the "Open tasks" card on `requires_continuation_approval`.
- `frontend/src/features/work-reports/components/period-activity-editor.tsx` — disable the per-row "Continue existing task" prompt when gated.
- `frontend/openapi.json` + `frontend/src/types/openapi.ts` — regenerated from the live backend spec.

**Frontend — new route:**
- `frontend/src/app/(app)/attendance/continuation/[id]/page.tsx`

---

## Task 1: Forward working-day helper

**Files:**
- Modify: `backend/app/modules/calendar/working_days.py`
- Test: `backend/tests/test_working_days_forward.py` (new)

**Interfaces:**
- Produces: `next_working_day(db: Session, reference: date, *, max_lookahead_days: int = 90) -> date | None` and `add_working_days(db: Session, start: date, steps: int, *, max_lookahead_days: int = 90) -> date | None`, both consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_working_days_forward.py`:

```python
"""next_working_day / add_working_days — forward counterparts to
previous_working_day, added for WorkItem's working-day due-date math
(Phase 2 lump-sum continuation approval)."""
from datetime import date

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.working_days import add_working_days, next_working_day


def _event(db, *, event_date, event_type):
    ev = CalendarEvent(event_date=event_date, title="Test", event_type=CalendarEventType(event_type))
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def test_next_working_day_plain_weekday(db):
    # Mon 2026-07-13 -> Tue 2026-07-14
    assert next_working_day(db, date(2026, 7, 13)) == date(2026, 7, 14)


def test_next_working_day_skips_weekend(db):
    # Fri 2026-07-10 -> Mon 2026-07-13
    assert date(2026, 7, 10).weekday() == 4
    assert next_working_day(db, date(2026, 7, 10)) == date(2026, 7, 13)


def test_next_working_day_skips_holiday(db):
    _event(db, event_date=date(2026, 7, 14), event_type="holiday")
    assert next_working_day(db, date(2026, 7, 13)) == date(2026, 7, 15)


def test_next_working_day_honours_working_override(db):
    # A declared working Saturday counts even though it's a weekend.
    assert date(2026, 7, 11).weekday() == 5  # Saturday
    _event(db, event_date=date(2026, 7, 11), event_type="working_day")
    assert next_working_day(db, date(2026, 7, 10)) == date(2026, 7, 11)


def test_add_working_days_zero_returns_start(db):
    assert add_working_days(db, date(2026, 7, 13), 0) == date(2026, 7, 13)


def test_add_working_days_one_plain(db):
    assert add_working_days(db, date(2026, 7, 13), 1) == date(2026, 7, 14)


def test_add_working_days_skips_weekend(db):
    # Fri 2026-07-10 + 1 working day -> Mon 2026-07-13.
    assert add_working_days(db, date(2026, 7, 10), 1) == date(2026, 7, 13)


def test_add_working_days_skips_weekend_and_holiday(db):
    # Fri 2026-07-10 + 2 working days: Sat/Sun skipped, Mon is a holiday too
    # -> Tue 2026-07-14.
    _event(db, event_date=date(2026, 7, 13), event_type="holiday")
    assert add_working_days(db, date(2026, 7, 10), 2) == date(2026, 7, 14)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest tests/test_working_days_forward.py -v`
Expected: FAIL — `ImportError: cannot import name 'next_working_day'`.

- [ ] **Step 3: Implement**

In `backend/app/modules/calendar/working_days.py`, after `previous_working_day` (currently ending at line 95), add:

```python
def next_working_day(
    db: Session,
    reference: date,
    *,
    max_lookahead_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> date | None:
    """The first working day strictly after ``reference``. Forward mirror of
    :func:`previous_working_day`. Returns ``None`` if none is found within
    ``max_lookahead_days`` (a misconfigured calendar)."""
    latest = reference + timedelta(days=max_lookahead_days)
    cursor = reference + timedelta(days=1)
    non_working, working_overrides = load_calendar_overrides(db, cursor, latest)
    while cursor <= latest:
        if is_working_day(
            cursor, non_working=non_working, working_overrides=working_overrides
        ):
            return cursor
        cursor += timedelta(days=1)
    return None


def add_working_days(
    db: Session,
    start: date,
    steps: int,
    *,
    max_lookahead_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> date | None:
    """``start`` plus ``steps`` WORKING days (``start`` itself is never counted
    as a step: ``steps=0`` returns ``start`` unchanged). Used for WorkItem due
    dates: ``due = add_working_days(db, started_on, target_days - 1)``, so a
    1-day allowed duration is due the same day it starts, and a 2-day duration
    is due the next WORKING day (weekends/company holidays skipped).

    Returns ``None`` if it cannot resolve within ``max_lookahead_days`` extra
    days beyond the naive count (a misconfigured calendar) — the caller
    decides the fallback.
    """
    if steps <= 0:
        return start
    latest = start + timedelta(days=max_lookahead_days + steps)
    non_working, working_overrides = load_calendar_overrides(db, start, latest)
    cursor = start
    remaining = steps
    while remaining > 0 and cursor <= latest:
        cursor += timedelta(days=1)
        if is_working_day(
            cursor, non_working=non_working, working_overrides=working_overrides
        ):
            remaining -= 1
    return cursor if remaining == 0 else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest tests/test_working_days_forward.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/calendar/working_days.py backend/tests/test_working_days_forward.py
git commit -m "feat(calendar): add next_working_day/add_working_days helpers"
```

---

## Task 2: Switch WorkItem due-date math to working days

**Files:**
- Modify: `backend/app/modules/work_reports/work_items.py`
- Modify: `backend/app/modules/work_reports/models.py` (docstring only)
- Modify: `backend/app/modules/work_reports/service.py:1506,1888` (call-site — none, `resolve_task_work_item` already receives `db`)
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_task_continuation.py`

**Interfaces:**
- Consumes: `add_working_days(db, start, steps) -> date | None` from Task 1.
- Produces: `compute_due_date(db: Session, started_on: date, target_days: int) -> date` (signature changed — was `compute_due_date(started_on, target_days)`), consumed inside `resolve_task_work_item` (same file) and by every test that calls it directly.

- [ ] **Step 1: Update the due-date tests for working-day semantics**

In `backend/tests/test_task_continuation.py`, replace lines 105–139 (the "due-date rule (pure)" block, from the `# --- due-date rule (pure) ---` comment through `test_due_date_matches_frontend_preview`) with:

```python
# --------------------------------------------------------------------------
# due-date rule (working days — Phase 2)
# --------------------------------------------------------------------------
def test_due_date_one_day(db):
    assert compute_due_date(db, date(2026, 7, 10), 1) == date(2026, 7, 10)


def test_due_date_two_days(db):
    # Mon 2026-07-13 + 1 more WORKING day -> Tue 2026-07-14 (no weekend in the way).
    assert compute_due_date(db, date(2026, 7, 13), 2) == date(2026, 7, 14)


def test_due_date_three_days(db):
    assert compute_due_date(db, date(2026, 7, 13), 3) == date(2026, 7, 15)


def test_due_date_skips_weekend(db):
    # Fri 2026-07-10 + 2 more WORKING days -> Tue 2026-07-14 (Sat/Sun skipped).
    assert date(2026, 7, 10).weekday() == 4  # Friday
    assert compute_due_date(db, date(2026, 7, 10), 3) == date(2026, 7, 14)
    assert compute_due_date(db, date(2026, 7, 10), 3).weekday() == 1  # Tuesday


def test_due_date_target_days_clamped_to_one(db):
    # A zero/blank period must never push the deadline before the start.
    assert compute_due_date(db, date(2026, 7, 10), 0) == date(2026, 7, 10)


def test_due_date_skips_company_holiday(db):
    from app.modules.calendar.models import CalendarEvent, CalendarEventType

    ev = CalendarEvent(
        event_date=date(2026, 7, 14), title="Holiday", event_type=CalendarEventType.holiday
    )
    db.add(ev)
    db.commit()
    # Mon 2026-07-13 + 1 working day would normally be Tue 2026-07-14, but
    # that date is a declared holiday, so it lands on Wed 2026-07-15.
    assert compute_due_date(db, date(2026, 7, 13), 2) == date(2026, 7, 15)
```

Then, in the same file, find `test_flag_off_creates_no_work_item` (currently taking no `flag_on` fixture, relying on the default being OFF) and its neighbouring `due_date` assertion, which is now wrong (calendar-day math). Replace the whole function:

```python
@pytest.fixture()
def flag_off():
    prev = settings.TASK_CONTINUATION_ENABLED
    settings.TASK_CONTINUATION_ENABLED = False
    try:
        yield
    finally:
        settings.TASK_CONTINUATION_ENABLED = prev


def test_flag_off_creates_no_work_item(flag_off, client, author, pm_header, db):
    a = author()
    _, sub = _task_sub(client, pm_header, period=2)
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY).json()
    assert r["tasks"][0]["work_item_id"] is None
    # Legacy per-row dates still stamped (calendar-day math — the legacy path
    # never calls compute_due_date/add_working_days at all).
    assert r["tasks"][0]["due_date"] == (TODAY + timedelta(days=1)).isoformat()
    assert db.query(WorkItem).count() == 0
    # No open-tasks surfaced while disabled.
    ot = client.get(OPEN_TASKS, headers=a["header"],
                    params={"report_date": TODAY.isoformat()}).json()
    assert ot["items"] == []
```

(The `@pytest.fixture() def flag_off` block goes just above `test_flag_off_creates_no_work_item`, near the existing `flag_on` fixture at the top of the file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest tests/test_task_continuation.py -k "due_date or flag_off" -v`
Expected: FAIL — `TypeError: compute_due_date() takes 2 positional arguments but 3 were given` (or similar), and `test_flag_off_creates_no_work_item` fails because the flag now defaults True without `flag_off`.

- [ ] **Step 3: Implement — work_items.py**

In `backend/app/modules/work_reports/work_items.py`:

Replace the module docstring's "Scope: TASK_BASED only..." line is unchanged, but update the import block and `compute_due_date`:

```python
from app.modules.calendar.working_days import add_working_days
```//(add this import near the top, after the existing `from sqlalchemy import func, select` line)

Replace the existing `compute_due_date` function:

```python
def compute_due_date(db: Session, started_on: date, target_days: int) -> date:
    """Fixed deadline in WORKING days, start day counting as day 1: a 1-day
    allowed duration is due the same day it starts; a 2-day duration is due
    the NEXT working day (weekends/company holidays skipped by
    calendar.working_days.add_working_days), and so on. target_days is
    clamped to >= 1 so a blank/zero benchmark period can never push the
    deadline before the start.

    Falls back to started_on itself if the company calendar cannot resolve a
    working day within the lookahead window (a misconfigured calendar) rather
    than raising mid-save — this should never happen in practice."""
    steps = max(1, target_days) - 1
    due = add_working_days(db, started_on, steps)
    return due if due is not None else started_on
```

Update the START branch inside `resolve_task_work_item` (the only call site) to pass `db`:

```python
            due_date=compute_due_date(db, started_on, target_days),
```

(This is the only change needed inside `resolve_task_work_item` for this task — the LINK branch/approval gate is Task 5.)

- [ ] **Step 4: Update the WorkItem model docstring**

In `backend/app/modules/work_reports/models.py`, in the `WorkItem` class docstring, change:

```
    due_date is FROZEN at creation (started_on + target_days - 1, calendar days)
    and never recomputed — a later change to the sub-activity's benchmark master
    must not move an in-flight deadline.
```

to:

```
    due_date is FROZEN at creation (started_on + (target_days - 1) WORKING days,
    via calendar.working_days.add_working_days — Phase 2) and never recomputed —
    a later change to the sub-activity's benchmark master must not move an
    in-flight deadline.
```

- [ ] **Step 5: Flip the feature flag default**

In `backend/app/core/config.py`, change:

```python
    TASK_CONTINUATION_ENABLED: bool = False
```

to:

```python
    TASK_CONTINUATION_ENABLED: bool = True
```

and update the comment immediately above it (currently starting "Task continuation (work_items). Off by default...") to:

```python
    # Task continuation (work_items). ON by default since Phase 2 (lump-sum
    # continuation approval) builds directly on this engine. When true, saving
    # a TASK_BASED/TASK_STATUS_ONLY/TASK_WITH_QUANTITY row creates/links a
    # WorkItem so one activity can span several daily reports with a fixed
    # (working-day) deadline. The frontend reads the mirror flag
    # NEXT_PUBLIC_FEATURE_TASK_CONTINUATION; keep the two in step per
    # environment.
```

In `backend/.env.example`, add near the `ENABLE_API_DOCS` block:

```
TASK_CONTINUATION_ENABLED=true
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest tests/test_task_continuation.py -v`
Expected: PASS — all due-date tests pass with working-day math; `test_flag_off_creates_no_work_item` passes using the new `flag_off` fixture; every other existing test in the file still passes unchanged (they only exercise 1–2 day periods on weekdays, where working-day and calendar-day math agree, per the fixtures' chosen dates — spot-check any failures against their specific dates and adjust only if a fixture happens to straddle a weekend).

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/work_reports/work_items.py backend/app/modules/work_reports/models.py backend/app/core/config.py backend/.env.example backend/tests/test_task_continuation.py
git commit -m "feat(work-items): compute due dates in working days, not calendar days"
```

---

## Task 3: Tag lump-sum task rows in the validation snapshot

**Files:**
- Modify: `backend/app/modules/work_reports/service.py:524-560`

**Interfaces:**
- Produces: `snap["is_lumpsum_task"]: bool` in the dict returned by `_validate_tasks`, consumed by Task 5's approval gate.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_task_continuation.py` (near the other TASK_BASED tests):

```python
def test_task_with_quantity_never_flagged_lumpsum(flag_on, client, author, pm_header, db):
    """TASK_WITH_QUANTITY rows must never be treated as lump-sum — this is the
    guard that keeps Phase 2's continuation-approval gate off quantity tasks."""
    a = author()
    aa = client.post("/api/v1/activity-master/activities",
                     json={"name": "Quantity Task"}, headers=pm_header).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{aa['id']}/sub-activities",
        json={"name": "QTask", "benchmark_type": "TASK_WITH_QUANTITY",
              "relevant_count_field": "pages", "benchmark_value": 100,
              "benchmark_period_days": 1},
        headers=pm_header,
    ).json()
    r = _post_report(client, a["header"], project_id=a["project"].id,
                     sub_id=sub["id"], on_date=TODAY, tags=0).json()
    # A TASK_WITH_QUANTITY row still gets a WorkItem (task-bearing), but the
    # snapshot distinguishes it from a lump-sum row — asserted indirectly here
    # via the work item existing and the row not being blocked (Task 5 adds
    # the actual gate; this test only pins the snapshot classification via the
    # public surface available at this point: the row saves successfully).
    assert r["tasks"][0]["work_item_id"] is not None
```

- [ ] **Step 2: Run test to verify it currently passes (baseline) then implement**

Run: `docker exec wms-backend-1 pytest tests/test_task_continuation.py::test_task_with_quantity_never_flagged_lumpsum -v`
Expected: PASS already (this step only proves the row still saves before the snapshot field is added; the field itself is exercised end-to-end by Task 5's tests, not observable via the API response). Proceed to implement regardless — this is a foundational field the gate needs.

- [ ] **Step 3: Implement**

In `backend/app/modules/work_reports/service.py`, inside `_validate_tasks`, change line 545 (`is_task_based = sub.benchmark_type in TASK_BENCHMARK_TYPES`) to also compute the lump-sum flag using the existing `is_lumpsum_unit_row` helper (already imported in this file — confirm the import list at the top includes `is_lumpsum_unit_row` from `app.modules.activity_master.models`; it is already used at line 551):

```python
            is_task_based = sub.benchmark_type in TASK_BENCHMARK_TYPES
            is_lumpsum_task = is_lumpsum_unit_row(sub.benchmark_type, sub.relevant_count_field)
            benchmark_period_days = sub.benchmark_period_days
```

Then in the `else:` branch a few lines down (the "No Activity Master selection at all" branch, currently setting `exception_code = None`, `count_field = None`, `count_value = None`), add:

```python
        else:
            # No Activity Master selection at all — nothing to benchmark, so
            # nothing to except, and no mode that could take a chosen unit.
            exception_code = None
            count_field = None
            count_value = None
            is_lumpsum_task = False
```

(`is_lumpsum_task` must be initialized before the `if getattr(task, "sub_activity_id", None) is not None:` branch, alongside the existing `is_task_based = False` initialization near line 487 — add `is_lumpsum_task = False` on the line right after it.)

Finally, add the new key to the snapshot dict appended at line 597:

```python
        snapshots.append({
            "project_name": project.name,
            "project_code": project.code,
            "project_job_code_code": job_code_code,
            "sub_activity_name": sub_activity_name,
            "activity_name": activity_name,
            "activity_type": activity_type,
            "is_task_based": is_task_based,
            "is_lumpsum_task": is_lumpsum_task,
            "benchmark_period_days": benchmark_period_days,
            "benchmark_exception_code": exception_code,
            "count_field": count_field,
            "count_value": count_value,
            "maintenance_plant_code": maintenance_plant_code,
```

(Keep every other existing key in that dict literal unchanged — only the `"is_lumpsum_task"` line is new.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest tests/test_task_continuation.py -v`
Expected: PASS (no regressions; the new field is additive and unused until Task 5).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/work_reports/service.py backend/tests/test_task_continuation.py
git commit -m "feat(work-reports): tag lump-sum task rows in the validation snapshot"
```

---

## Task 4: `continuation_requests` module — model, schema, migration

**Files:**
- Create: `backend/app/modules/continuation_requests/__init__.py` (empty)
- Create: `backend/app/modules/continuation_requests/models.py`
- Create: `backend/app/modules/continuation_requests/schemas.py`
- Create: `backend/alembic/versions/0074_continuation_requests.py`

**Interfaces:**
- Produces: `ContinuationRequest` ORM model, `ContinuationRequestStatus` enum, and the four schema classes, consumed by Task 5 (service.py) and Task 6 (router.py).

- [ ] **Step 1: Create the model**

Create `backend/app/modules/continuation_requests/__init__.py` (empty file).

Create `backend/app/modules/continuation_requests/models.py`:

```python
"""ContinuationRequest ORM model — Lump-sum Activity Continuation Approval
(Phase 2).

A dedicated request/approval record. Reuses the existing WorkItem
task-continuation engine (app.modules.work_reports.work_items) as its
subject and the existing Project Head authorization (app.core.authz) +
notifications (app.modules.notifications.service) infrastructure — this
table only adds the missing approval gate + audit trail. Deliberately NOT
built on leave_requests (leave-specific: leave_type, date-range, balance
ledger) or activity_requests (a different action — requesting a NEW
activity, not continuing an existing one). See migration 0074.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import UUIDMixin


class ContinuationRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ContinuationRequest(UUIDMixin, Base):
    __tablename__ = "continuation_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # The specific activity instance this approval applies to. RESTRICT: a
    # WorkItem cannot be deleted while a continuation request still
    # references it (mirrors work_report_tasks.work_item_id's own RESTRICT).
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=False
    )
    # Denormalised from the WorkItem so routing/scoping queries never need a
    # join. The project WHO reviews is resolved against — always the
    # project's CURRENT head_employee_id via app.core.authz, never a frozen
    # head id (matches leave_requests.routed_project_id's model exactly: this
    # column is the historical PROJECT only).
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    sub_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    # Audit snapshot of the WorkItem at request time — never re-read from the
    # WorkItem afterward (WorkItem.due_date is itself frozen at creation, so
    # this can never drift from it).
    original_report_date: Mapped[date] = mapped_column(Date, nullable=False)
    allowed_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The report date the employee was attempting to continue on when the
    # approval gate blocked them.
    continuation_date: Mapped[date] = mapped_column(Date, nullable=False)

    # VARCHAR + CHECK (not a native Postgres enum) — follows the
    # activity_requests.status / benchmark_type / report_mode precedent.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ContinuationRequestStatus.pending.value
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="continuation_requests_status_valid",
        ),
        CheckConstraint(
            "continuation_date > due_date", name="continuation_requests_date_after_due"
        ),
        Index("continuation_requests_employee_idx", "employee_id"),
        Index("continuation_requests_work_item_idx", "work_item_id"),
        Index("continuation_requests_project_idx", "project_id"),
        Index("continuation_requests_status_idx", "status"),
        # One PENDING request per WorkItem — the DB-level guard for "no
        # duplicate pending continuation requests" (service.py pre-checks the
        # same predicate for a clean error message; this is the authoritative
        # guard against a concurrent/duplicate insert).
        Index(
            "continuation_requests_one_pending_per_item_uq",
            "work_item_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
```

- [ ] **Step 2: Create the schemas**

Create `backend/app/modules/continuation_requests/schemas.py`:

```python
"""ContinuationRequest pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.modules.continuation_requests.models import ContinuationRequestStatus


class ContinuationRequestCreate(BaseModel):
    """Body sent when an employee clicks 'Request Continuation Approval'."""
    work_item_id: uuid.UUID
    continuation_date: date


class ContinuationReviewBody(BaseModel):
    comment: str | None = None


class ContinuationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    work_item_id: uuid.UUID
    project_id: uuid.UUID
    sub_activity_id: uuid.UUID
    original_report_date: date
    allowed_duration_days: int
    due_date: date
    continuation_date: date
    status: ContinuationRequestStatus
    requested_at: datetime
    reviewer_id: uuid.UUID | None = None
    decision_comment: str | None = None
    decided_at: datetime | None = None

    # Display-only, resolved by the service (never persisted).
    employee_name: str = ""
    project_name: str = ""
    project_code: str = ""
    activity_name: str | None = None
    sub_activity_name: str = ""
    reviewer_name: str | None = None
    # Who this request is CURRENTLY routed to — resolved fresh at read time,
    # never frozen (matches leave's routing model, spec §14).
    routed_to_name: str | None = None
    routed_to_role: str | None = None  # "head" | "manager" | None


class ContinuationRequestPage(BaseModel):
    items: list[ContinuationRequestOut] = []
    total: int
    limit: int
    offset: int
```

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/0074_continuation_requests.py`. First confirm the current head revision:

Run: `docker exec wms-backend-1 alembic heads`
Expected: `0073_leave_routed_project (head)`

```python
"""0074 continuation requests

Adds the `continuation_requests` table — Lump-sum Activity Continuation
Approval (Phase 2). One row per continuation-approval request against a
specific WorkItem (app.modules.work_reports.models.WorkItem). See
app/modules/continuation_requests/models.py for the full column rationale.

Revision ID: 0074_continuation_requests
Revises: 0073_leave_routed_project
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0074_continuation_requests"
down_revision: Union[str, None] = "0073_leave_routed_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "continuation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sub_activity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_report_date", sa.Date(), nullable=False),
        sa.Column("allowed_duration_days", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("continuation_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="continuation_requests_status_valid",
        ),
        sa.CheckConstraint(
            "continuation_date > due_date", name="continuation_requests_date_after_due"
        ),
    )
    op.create_index(
        "continuation_requests_employee_idx", "continuation_requests", ["employee_id"]
    )
    op.create_index(
        "continuation_requests_work_item_idx", "continuation_requests", ["work_item_id"]
    )
    op.create_index(
        "continuation_requests_project_idx", "continuation_requests", ["project_id"]
    )
    op.create_index(
        "continuation_requests_status_idx", "continuation_requests", ["status"]
    )
    op.create_index(
        "continuation_requests_one_pending_per_item_uq",
        "continuation_requests",
        ["work_item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("continuation_requests_one_pending_per_item_uq", table_name="continuation_requests")
    op.drop_index("continuation_requests_status_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_project_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_work_item_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_employee_idx", table_name="continuation_requests")
    op.drop_table("continuation_requests")
```

- [ ] **Step 4: Run the migration**

Run: `docker exec wms-backend-1 alembic upgrade head`
Expected: `Running upgrade 0073_leave_routed_project -> 0074_continuation_requests, 0074 continuation requests`, no errors.

Run: `docker exec wms-backend-1 alembic downgrade -1 && docker exec wms-backend-1 alembic upgrade head`
Expected: both succeed cleanly (proves `downgrade()` is correct before it's ever needed for real).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/continuation_requests/__init__.py backend/app/modules/continuation_requests/models.py backend/app/modules/continuation_requests/schemas.py backend/alembic/versions/0074_continuation_requests.py
git commit -m "feat(continuation-requests): add model, schemas, and migration"
```

---

## Task 5: `continuation_requests` service + approval gate in the continuation engine

**Files:**
- Create: `backend/app/modules/continuation_requests/service.py`
- Modify: `backend/app/modules/work_reports/work_items.py` (`resolve_task_work_item`, `get_open_work_items`)
- Modify: `backend/app/modules/work_reports/schemas.py` (`OpenTaskOut`)
- Test: `backend/tests/test_continuation_requests.py` (new)

**Interfaces:**
- Consumes: `ContinuationRequest`/`ContinuationRequestStatus` (Task 4), `authz.project_head_employee_id`/`can_review_report`/`reviewable_project_ids` (existing), `notifications.service.create_notification` (existing), `is_lumpsum_unit_row` (existing, `activity_master.models`).
- Produces: `has_approved_continuation(db, *, work_item_id) -> bool`, `latest_requests_by_work_item(db, work_item_ids) -> dict[uuid.UUID, ContinuationRequest]`, `create_continuation_request`, `list_pending`, `list_all`, `get_continuation_request`, `approve_continuation_request`, `reject_continuation_request` — consumed by Task 6 (router) and by `work_items.py` in this same task.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_continuation_requests.py`:

```python
"""Lump-sum Activity Continuation Approval (Phase 2).

Covers: gate blocking/allowing continuation, request creation + duplicate
prevention, Head resolution + reassignment, PM (line-manager) fallback,
approve/reject, unauthorized/self-approval, notifications, and non-regression
of TASK_WITH_QUANTITY continuation and existing work-item behaviour.
"""
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.modules.continuation_requests.models import ContinuationRequest
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports.models import WorkItem

BASE = "/api/v1/work-reports"
OPEN_TASKS = "/api/v1/work-reports/open-tasks"
CR = "/api/v1/continuation-requests"
TODAY = date.today()


@pytest.fixture()
def flag_on():
    prev = settings.TASK_CONTINUATION_ENABLED
    settings.TASK_CONTINUATION_ENABLED = True
    try:
        yield
    finally:
        settings.TASK_CONTINUATION_ENABLED = prev


@pytest.fixture()
def author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1", manager_id=None, head_id=None):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, manager_id=manager_id)
        p = make_project(code=proj_code, status=ProjectStatus.active, head_employee_id=head_id)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def pm_header(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _lumpsum_sub(client, admin, *, name="Lumpsum", period=1):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_STATUS_ONLY"}, headers=admin,
    ).json()
    client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": period}, headers=admin,
    )
    return a, sub


def _quantity_task_sub(client, admin, *, name="Quantity", period=1):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity {name}"}, headers=admin,
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_WITH_QUANTITY",
              "relevant_count_field": "pages", "benchmark_value": 100,
              "benchmark_period_days": period},
        headers=admin,
    ).json()
    return a, sub


def _post_report(client, header, *, project_id, sub_id, on_date, work_item_id=None, expect=201):
    task = {"project_id": str(project_id), "description": "work", "sub_activity_id": sub_id}
    if work_item_id is not None:
        task["work_item_id"] = str(work_item_id)
    res = client.post(BASE, headers=header, json={
        "report_date": on_date.isoformat(), "day_status": "work_at_office",
        "location": "chennai", "tasks": [task],
    })
    assert res.status_code == expect, res.text
    return res


def _start_work_item(client, header, *, project_id, sub_id, on_date):
    r = _post_report(client, header, project_id=project_id, sub_id=sub_id, on_date=on_date).json()
    return r["tasks"][0]["work_item_id"]


# --------------------------------------------------------------------------
# 1/2/3: within-duration continues; overdue lump-sum is blocked; approval unblocks
# --------------------------------------------------------------------------

def test_within_duration_continues_normally(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=2)  # due_date = next WORKING day
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    # next_day (a calendar day ahead) is always <= due_date (the next WORKING
    # day, which never falls before the next calendar day) — still within the
    # allowed duration regardless of which weekday TODAY happens to be.
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=next_day, work_item_id=wi, expect=201)


def test_overdue_lumpsum_requires_approval(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)  # due the same day it starts
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)  # target_days=1 on a plain weekday -> already overdue
    res = _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                       on_date=next_day, work_item_id=wi, expect=403)
    assert "allowed duration" in res.json()["error"]["message"].lower()


def test_approval_unlocks_continuation(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)

    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()
    assert req["status"] == "pending"

    client.post(f"{CR}/{req['id']}/approve", headers=pm_header, json={})
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=next_day, work_item_id=wi, expect=201)


def test_rejection_keeps_continuation_blocked(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)

    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()
    client.post(f"{CR}/{req['id']}/reject", headers=pm_header, json={"comment": "not justified"})

    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=next_day, work_item_id=wi, expect=403)


def test_pending_request_keeps_continuation_blocked(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)

    client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    })
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=next_day, work_item_id=wi, expect=403)


# --------------------------------------------------------------------------
# duplicate prevention
# --------------------------------------------------------------------------

def test_duplicate_pending_request_returns_existing(flag_on, client, author, pm_header, db):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)

    body = {"work_item_id": wi, "continuation_date": next_day.isoformat()}
    r1 = client.post(CR, headers=a["header"], json=body).json()
    r2 = client.post(CR, headers=a["header"], json=body).json()
    assert r1["id"] == r2["id"]
    assert db.query(ContinuationRequest).filter_by(work_item_id=wi).count() == 1


# --------------------------------------------------------------------------
# routing / authorization
# --------------------------------------------------------------------------

def test_correct_head_receives_request(flag_on, client, make_user, make_employee, make_project,
                                        make_project_member, login, pm_header):
    head_u = make_user("head1@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H1", user_id=head_u.id)
    emp_u = make_user("emp1@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E2", user_id=emp_u.id)
    project = make_project(code="P-H1", status=ProjectStatus.active, head_employee_id=head.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("emp1@x.com")
    head_header = login("head1@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    pending = client.get(f"{CR}/pending", headers=head_header).json()
    assert any(r["id"] == req["id"] for r in pending)

    other_u = make_user("other1@x.com", role=UserRole.employee)
    make_employee(employee_code="O1", user_id=other_u.id)
    other_header = login("other1@x.com")
    pending_other = client.get(f"{CR}/pending", headers=other_header).json()
    assert not any(r["id"] == req["id"] for r in pending_other)


def test_no_head_falls_back_to_manager_and_pm_can_still_approve(
    flag_on, client, db, make_user, make_employee, make_project, make_project_member, login, pm_header,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    mgr_u = make_user("mgr1@x.com", role=UserRole.employee)
    mgr = make_employee(employee_code="M1", user_id=mgr_u.id)
    emp_u = make_user("emp2@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E3", user_id=emp_u.id, manager_id=mgr.id)
    project = make_project(code="P-NM", status=ProjectStatus.active, head_employee_id=None)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("emp2@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    })

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == mgr_u.id, Notification.type == "continuation_requested",
        )
    ).scalar_one_or_none()
    assert notif is not None

    req = db.execute(
        select(ContinuationRequest).where(ContinuationRequest.employee_id == emp.id)
    ).scalar_one()
    res = client.post(f"{CR}/{req.id}/approve", headers=pm_header, json={})
    assert res.status_code == 200, res.text


def test_reassigned_head_takes_over_review_authority(
    flag_on, client, db, make_user, make_employee, make_project, make_project_member, login, pm_header,
):
    head_a_u = make_user("heada@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HA", user_id=head_a_u.id)
    head_b_u = make_user("headb@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HB", user_id=head_b_u.id)
    project = make_project(code="P-RH", status=ProjectStatus.active, head_employee_id=head_a.id)

    emp_u = make_user("empr@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="ER", user_id=emp_u.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    emp_header = login("empr@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, emp_header, project_id=project.id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=emp_header, json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    project.head_employee_id = head_b.id
    db.add(project)
    db.commit()

    h_a = login("heada@x.com")
    res_a = client.post(f"{CR}/{req['id']}/approve", headers=h_a, json={})
    assert res_a.status_code == 403, res_a.text

    h_b = login("headb@x.com")
    res_b = client.post(f"{CR}/{req['id']}/approve", headers=h_b, json={})
    assert res_b.status_code == 200, res_b.text


def test_unauthorized_employee_cannot_approve(flag_on, client, author, pm_header, make_user, login):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    make_user("stranger@x.com", role=UserRole.employee)
    stranger = login("stranger@x.com")
    res = client.post(f"{CR}/{req['id']}/approve", headers=stranger, json={})
    assert res.status_code == 403, res.text


def test_self_approval_blocked(flag_on, client, author, pm_header, db):
    """The Project Head IS the requesting employee (self-routed) — the review
    endpoint must still 403, mirroring leave's self-review guard."""
    a = author()
    a["project"].head_employee_id = a["emp"].id
    db.add(a["project"])
    db.commit()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()
    res = client.post(f"{CR}/{req['id']}/approve", headers=a["header"], json={})
    assert res.status_code == 403, res.text


# --------------------------------------------------------------------------
# decisions: approve / reject + notifications
# --------------------------------------------------------------------------

def test_head_can_approve_and_notifies_employee(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    a = author()
    head_u = make_user("head3@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H3", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head3@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    res = client.post(f"{CR}/{req['id']}/approve", headers=head_header, json={"comment": "go ahead"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert res.json()["reviewer_id"] == str(head.id)

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id, Notification.type == "continuation_approved",
        )
    ).scalar_one_or_none()
    assert notif is not None


def test_head_can_reject_and_notifies_employee(
    flag_on, client, db, author, pm_header, make_user, make_employee, login,
):
    from sqlalchemy import select

    from app.modules.notifications.models import Notification

    a = author()
    head_u = make_user("head4@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H4", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head4@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    res = client.post(f"{CR}/{req['id']}/reject", headers=head_header, json={"comment": "not justified"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"

    notif = db.execute(
        select(Notification).where(
            Notification.user_id == a["user"].id, Notification.type == "continuation_rejected",
        )
    ).scalar_one_or_none()
    assert notif is not None

    pending = client.get(f"{CR}/pending", headers=head_header).json()
    assert not any(r["id"] == req["id"] for r in pending)


def test_pending_and_all_requests_reflect_decisions(flag_on, client, author, pm_header):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    pending_before = client.get(f"{CR}/pending", headers=pm_header).json()
    assert any(r["id"] == req["id"] for r in pending_before)

    client.post(f"{CR}/{req['id']}/approve", headers=pm_header, json={})

    pending_after = client.get(f"{CR}/pending", headers=pm_header).json()
    assert not any(r["id"] == req["id"] for r in pending_after)

    history = client.get(CR, headers=pm_header, params={"status": "approved"}).json()
    assert any(r["id"] == req["id"] for r in history["items"])
    assert history["total"] >= 1


def test_task_with_quantity_continuation_never_gated(flag_on, client, author, pm_header):
    """TASK_WITH_QUANTITY must continue exactly as before Phase 2 — never
    gated by the lump-sum continuation-approval check, even when overdue."""
    a = author()
    _, sub = _quantity_task_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)  # overdue for a 1-day period — would be blocked if lump-sum
    _post_report(client, a["header"], project_id=a["project"].id, sub_id=sub["id"],
                 on_date=next_day, work_item_id=wi, expect=201)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest tests/test_continuation_requests.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.continuation_requests.service'` and `404` for the unregistered `/continuation-requests` routes.

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/continuation_requests/service.py`:

```python
"""ContinuationRequest service — Lump-sum Activity Continuation Approval
(Phase 2).

Employees request approval to continue an overdue lump-sum WorkItem; the
project's CURRENT Head (or, with no Head, the employee's line manager as a
notification fallback — mirrors leave/service.py exactly) reviews. Head/PM
authorization reuses app.core.authz verbatim; nothing here duplicates it.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.activity_master.models import ActivityMaster
from app.modules.continuation_requests.models import ContinuationRequest, ContinuationRequestStatus
from app.modules.continuation_requests.schemas import ContinuationRequestCreate
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import Project
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import WorkItem
from app.shared.errors import AppError


# ── notification helpers (mirrors leave/service.py's _push/_notify_*) ──────

def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None, target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(
            db, user_id=user_id, type_=type_, title=title, message=message,
            entity_type="continuation_request", entity_id=entity_id, target_url=target_url,
        )
        db.commit()
    except Exception:
        db.rollback()


def _notify_reviewer(db: Session, employee: Employee, req: ContinuationRequest, sub_name: str) -> None:
    """Notify whoever must act: the CURRENT Head of req.project_id if one is
    assigned (and isn't the requester), else the employee's line manager —
    mirrors leave.service._notify_routed_approver's fallback exactly (spec:
    PM-fallback = line manager, not the project_managers assignment table).
    Resolved fresh, never off a frozen value (spec §14)."""
    target_url = f"/attendance?tab=lump-sum-activity&queue=pending&id={req.id}"
    head_id = authz.project_head_employee_id(db, req.project_id)
    if head_id is not None and head_id != employee.id:
        head = db.get(Employee, head_id)
        if head is not None and head.user_id is not None:
            _push(
                db, head.user_id, "continuation_requested",
                f"{employee.full_name} needs continuation approval",
                f"{employee.full_name} requested continuation approval for "
                f"'{sub_name}' beyond its allowed duration.",
                req.id, target_url,
            )
            return
    if employee.manager_id is None:
        return
    mgr = db.get(Employee, employee.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(
        db, mgr.user_id, "continuation_requested",
        f"{employee.full_name} needs continuation approval",
        f"{employee.full_name} requested continuation approval for '{sub_name}' "
        "beyond its allowed duration. No Project Head is assigned to this project.",
        req.id, target_url,
    )


def _notify_employee(db: Session, employee_id: uuid.UUID, type_: str, title: str, message: str,
                     req_id: uuid.UUID) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.user_id is None:
        return
    _push(db, emp.user_id, type_, title, message, req_id)


# ── name/routing display resolution ─────────────────────────────────────────

def _attach_names(db: Session, rows: list[ContinuationRequest]) -> None:
    if not rows:
        return
    employee_ids = {r.employee_id for r in rows} | {r.reviewer_id for r in rows if r.reviewer_id}
    project_ids = {r.project_id for r in rows}
    sub_ids = {r.sub_activity_id for r in rows}

    employees = {
        e.id: e for e in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars().all()
    }
    projects = {
        p.id: p for p in db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
    }
    subs = {
        s.id: s for s in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(sub_ids))).scalars().all()
    }
    parent_ids = {s.parent_id for s in subs.values() if s.parent_id}
    parents = (
        {p.id: p for p in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(parent_ids))).scalars().all()}
        if parent_ids else {}
    )

    for r in rows:
        emp = employees.get(r.employee_id)
        proj = projects.get(r.project_id)
        sub = subs.get(r.sub_activity_id)
        parent = parents.get(sub.parent_id) if sub and sub.parent_id else None
        reviewer = employees.get(r.reviewer_id) if r.reviewer_id else None

        r.employee_name = emp.full_name if emp else ""  # type: ignore[attr-defined]
        r.project_name = proj.name if proj else ""  # type: ignore[attr-defined]
        r.project_code = proj.code if proj else ""  # type: ignore[attr-defined]
        r.sub_activity_name = sub.name if sub else ""  # type: ignore[attr-defined]
        r.activity_name = parent.name if parent else None  # type: ignore[attr-defined]
        r.reviewer_name = reviewer.full_name if reviewer else None  # type: ignore[attr-defined]

        head_id = authz.project_head_employee_id(db, r.project_id)
        if head_id is not None and head_id != r.employee_id:
            head = employees.get(head_id) or db.get(Employee, head_id)
            r.routed_to_name = head.full_name if head else None  # type: ignore[attr-defined]
            r.routed_to_role = "head"  # type: ignore[attr-defined]
        elif emp is not None and emp.manager_id is not None:
            mgr = employees.get(emp.manager_id) or db.get(Employee, emp.manager_id)
            r.routed_to_name = mgr.full_name if mgr else None  # type: ignore[attr-defined]
            r.routed_to_role = "manager"  # type: ignore[attr-defined]
        else:
            r.routed_to_name = None  # type: ignore[attr-defined]
            r.routed_to_role = None  # type: ignore[attr-defined]


# ── the gate work_items.py consults ─────────────────────────────────────────

def has_approved_continuation(db: Session, *, work_item_id: uuid.UUID) -> bool:
    """Whether an APPROVED continuation request exists for this work item —
    the single predicate work_items.resolve_task_work_item gates on. Approval
    is permanent for the life of the item (its due_date never moves and it
    stays overdue until completed), so this never expires."""
    return db.execute(
        select(ContinuationRequest.id).where(
            ContinuationRequest.work_item_id == work_item_id,
            ContinuationRequest.status == ContinuationRequestStatus.approved.value,
        ).limit(1)
    ).first() is not None


def latest_requests_by_work_item(
    db: Session, work_item_ids,
) -> dict[uuid.UUID, ContinuationRequest]:
    """The most recent continuation request per work item (any status) — the
    one reflecting each item's CURRENT continuation-approval state. Consumed
    by work_items.get_open_work_items to annotate open-task suggestions."""
    ids = list(work_item_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(ContinuationRequest)
        .where(ContinuationRequest.work_item_id.in_(ids))
        .order_by(ContinuationRequest.requested_at)
    ).scalars().all()
    latest: dict[uuid.UUID, ContinuationRequest] = {}
    for r in rows:
        latest[r.work_item_id] = r  # later rows overwrite earlier ones
    _attach_names(db, list(latest.values()))
    return latest


def _pending_for_work_item(db: Session, work_item_id: uuid.UUID) -> ContinuationRequest | None:
    return db.execute(
        select(ContinuationRequest).where(
            ContinuationRequest.work_item_id == work_item_id,
            ContinuationRequest.status == ContinuationRequestStatus.pending.value,
        )
    ).scalar_one_or_none()


def _fetch(db: Session, req_id: uuid.UUID) -> ContinuationRequest:
    req = db.get(ContinuationRequest, req_id)
    if req is None:
        raise AppError("not_found", "Continuation request not found.", 404)
    return req


def _fetch_locked(db: Session, req_id: uuid.UUID) -> ContinuationRequest:
    req = db.execute(
        select(ContinuationRequest).where(ContinuationRequest.id == req_id).with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise AppError("not_found", "Continuation request not found.", 404)
    return req


# ── public API ───────────────────────────────────────────────────────────────

def create_continuation_request(
    db: Session, actor: User, data: ContinuationRequestCreate
) -> ContinuationRequest:
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can request continuation approval.", 403)

    item = db.get(WorkItem, data.work_item_id)
    if item is None:
        raise AppError("not_found", "Work item not found.", 404)
    if item.employee_id != employee.id:
        raise AppError("forbidden", "You can only request continuation for your own tasks.", 403)
    if item.completed_on is not None:
        raise AppError("validation_error", "This task is already completed.", 422)
    if data.continuation_date <= item.due_date:
        raise AppError(
            "validation_error",
            "This task is still within its allowed duration — no approval is needed yet.",
            422,
        )

    # Idempotent: a retry (double click / refresh) must not create a second
    # pending request for the same situation — return the existing one.
    existing = _pending_for_work_item(db, item.id)
    if existing is not None:
        _attach_names(db, [existing])
        return existing

    sub = db.get(ActivityMaster, item.sub_activity_id)
    req = ContinuationRequest(
        employee_id=employee.id,
        work_item_id=item.id,
        project_id=item.project_id,
        sub_activity_id=item.sub_activity_id,
        original_report_date=item.started_on,
        allowed_duration_days=item.target_days,
        due_date=item.due_date,
        continuation_date=data.continuation_date,
        status=ContinuationRequestStatus.pending.value,
    )
    db.add(req)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent duplicate create — the partial unique
        # index rejected the second pending row. Fall back to the winner.
        db.rollback()
        existing = _pending_for_work_item(db, item.id)
        if existing is None:
            raise
        _attach_names(db, [existing])
        return existing
    db.refresh(req)

    _attach_names(db, [req])
    _notify_reviewer(db, employee, req, sub.name if sub else "this activity")
    return req


def _reviewable_project_ids_or_all(db: Session, actor: User) -> set[uuid.UUID] | None:
    """None means 'no project filter' — PM reviews everything."""
    if actor.role == UserRole.project_manager:
        return None
    return authz.reviewable_project_ids(db, actor)


def list_pending(db: Session, actor: User) -> list[ContinuationRequest]:
    project_ids = _reviewable_project_ids_or_all(db, actor)
    if project_ids is not None and not project_ids:
        return []
    stmt = select(ContinuationRequest).where(
        ContinuationRequest.status == ContinuationRequestStatus.pending.value
    )
    if project_ids is not None:
        stmt = stmt.where(ContinuationRequest.project_id.in_(project_ids))
    me = _current_employee(db, actor)
    if me is not None:
        # A reviewer never sees their own request in the queue they'd have to
        # act on — they cannot approve it anyway (self-review is forbidden).
        stmt = stmt.where(ContinuationRequest.employee_id != me.id)
    rows = list(db.execute(stmt.order_by(ContinuationRequest.requested_at)).scalars().all())
    _attach_names(db, rows)
    return rows


def list_all(
    db: Session, actor: User, *, status: str | None, limit: int, offset: int,
) -> tuple[list[ContinuationRequest], int]:
    from sqlalchemy import func

    project_ids = _reviewable_project_ids_or_all(db, actor)
    if project_ids is not None and not project_ids:
        return [], 0
    stmt = select(ContinuationRequest)
    if project_ids is not None:
        stmt = stmt.where(ContinuationRequest.project_id.in_(project_ids))
    if status is not None:
        stmt = stmt.where(ContinuationRequest.status == status)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(ContinuationRequest.requested_at.desc()).limit(limit).offset(offset)
        ).scalars().all()
    )
    _attach_names(db, rows)
    return rows, total


def _assert_can_review(db: Session, actor: User, req: ContinuationRequest) -> None:
    if not authz.can_review_report(db, actor, {req.project_id}):
        raise AppError(
            "forbidden",
            "Only a project manager or this request's assigned Project Head can review it.",
            403,
        )
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError(
            "forbidden",
            "You can't review your own continuation request — another reviewer has to decide it.",
            403,
        )


def get_continuation_request(db: Session, actor: User, req_id: uuid.UUID) -> ContinuationRequest:
    req = _fetch(db, req_id)
    if actor.role != UserRole.project_manager:
        me = _current_employee(db, actor)
        is_owner = me is not None and req.employee_id == me.id
        if not is_owner and not authz.can_review_report(db, actor, {req.project_id}):
            raise AppError("forbidden", "Not permitted.", 403)
    _attach_names(db, [req])
    return req


def approve_continuation_request(
    db: Session, actor: User, req_id: uuid.UUID, comment: str | None
) -> ContinuationRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != ContinuationRequestStatus.pending.value:
        raise AppError("validation_error", "This request has already been decided.", 422)

    reviewer = _current_employee(db, actor)
    req.status = ContinuationRequestStatus.approved.value
    req.reviewer_id = reviewer.id if reviewer else None
    req.decision_comment = comment
    req.decided_at = datetime.now(timezone.utc)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])
    sub = db.get(ActivityMaster, req.sub_activity_id)
    _notify_employee(
        db, req.employee_id, "continuation_approved", "Continuation approved",
        f"Your request to continue '{sub.name if sub else 'this activity'}' beyond "
        "its allowed duration was approved. You can continue reporting it.",
        req.id,
    )
    return req


def reject_continuation_request(
    db: Session, actor: User, req_id: uuid.UUID, comment: str | None
) -> ContinuationRequest:
    req = _fetch_locked(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != ContinuationRequestStatus.pending.value:
        raise AppError("validation_error", "This request has already been decided.", 422)

    reviewer = _current_employee(db, actor)
    req.status = ContinuationRequestStatus.rejected.value
    req.reviewer_id = reviewer.id if reviewer else None
    req.decision_comment = comment
    req.decided_at = datetime.now(timezone.utc)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])
    sub = db.get(ActivityMaster, req.sub_activity_id)
    _notify_employee(
        db, req.employee_id, "continuation_rejected", "Continuation rejected",
        f"Your request to continue '{sub.name if sub else 'this activity'}' beyond "
        "its allowed duration was rejected"
        + (f": {comment}" if comment else ".") + " You cannot continue this activity.",
        req.id,
    )
    return req
```

- [ ] **Step 4: Wire the approval gate into the continuation engine**

In `backend/app/modules/work_reports/work_items.py`, inside `resolve_task_work_item`'s LINK branch, insert the gate right before the `_apply_completion(...)` call (after the existing "already completed" guard, so ordering stays: ownership → project → sub-activity → date → already-completed → **approval gate** → completion):

```python
    is_resave = work_item_id in existing_links
    if item.completed_on is not None and not is_resave:
        raise AppError(
            "validation_error",
            "This task is already completed and cannot be continued.",
            422,
        )

    # Lump-sum continuation approval (Phase 2). Only a brand-NEW continuation
    # entry (never a resave of a row this report already had) on an OVERDUE
    # lump-sum item is gated — TASK_WITH_QUANTITY rows (snap["is_lumpsum_task"]
    # is False for them) are never touched by this check.
    if (
        not is_resave
        and snap.get("is_lumpsum_task")
        and report.report_date > item.due_date
    ):
        from app.modules.continuation_requests.service import has_approved_continuation

        if not has_approved_continuation(db, work_item_id=item.id):
            raise AppError(
                "forbidden",
                "This lump-sum activity's allowed duration has passed. Request "
                "continuation approval from the Project Head before continuing.",
                403,
            )

    _apply_completion(db, item, is_completed=is_completed, report=report, editable=editable)
    return {"work_item_id": item.id, **mirror_fields(item, report.report_date)}
```

Now extend `get_open_work_items` to surface the continuation-approval state for lump-sum items. Replace the whole function body with:

```python
def get_open_work_items(
    db: Session, *, employee_id: uuid.UUID, report_date: date
) -> list[dict]:
    """Unfinished work items the employee can continue in a report dated
    `report_date`. Lifecycle/overdue are evaluated relative to report_date (the
    report being written), not wall-clock today. Legacy NULL-linked rows are not
    represented here — only real work items. Ordered OVERDUE, DUE_TODAY, then
    IN_PROGRESS by nearest due date.

    Continuation is confined to a SINGLE Friday-Thursday benchmark cycle: an item
    may be continued only within the cycle that contains its originating
    started_on. Once report_date crosses into a later cycle the item drops out of
    the suggestions (it stays incomplete in the DB and keeps appearing as
    Not-Completed/Overdue in historical benchmark exports — see project rule).
    Re-selecting the same activity in the new cycle starts a fresh work item.

    Lump-sum continuation approval (Phase 2): an OVERDUE item whose
    sub-activity is a lump-sum/NON_QUANTITATIVE task (no relevant_count_field —
    see activity_master.models.is_lumpsum_unit_row) additionally carries
    requires_continuation_approval / continuation_status / continuation_request_id
    / continuation_routed_to, resolved from continuation_requests. A
    TASK_WITH_QUANTITY item is never gated — those four fields stay
    False/None/None/None for it, exactly as before Phase 2."""
    from app.modules.activity_master.models import is_lumpsum_unit_row

    report_cycle = compute_week_bounds(report_date)
    stmt = (
        select(
            WorkItem,
            ActivityMaster.parent_id.label("activity_id"),
            ActivityMaster.benchmark_type.label("benchmark_type"),
            ActivityMaster.relevant_count_field.label("relevant_count_field"),
        )
        .join(ActivityMaster, ActivityMaster.id == WorkItem.sub_activity_id)
        .where(
            WorkItem.employee_id == employee_id,
            WorkItem.completed_on.is_(None),
            WorkItem.started_on <= report_date,
        )
    )
    rows = db.execute(stmt).all()

    out: list[dict] = []
    lumpsum_ids: set[uuid.UUID] = set()
    for item, activity_id, benchmark_type, relevant_count_field in rows:
        if compute_week_bounds(item.started_on) != report_cycle:
            continue
        lc = lifecycle_of(item.due_date, item.completed_on, today=report_date)
        if is_lumpsum_unit_row(benchmark_type, relevant_count_field):
            lumpsum_ids.add(item.id)
        out.append({
            "work_item_id": item.id,
            "project_id": item.project_id,
            "project_code": item.project_code,
            "project_name": item.project_name,
            "activity_id": activity_id,
            "activity_name": item.activity_name,
            "sub_activity_id": item.sub_activity_id,
            "sub_activity_name": item.sub_activity_name,
            "started_on": item.started_on,
            "due_date": item.due_date,
            "target_days": item.target_days,
            "lifecycle": lc.value,
            "days_overdue": days_overdue_of(
                item.due_date, item.completed_on, today=report_date
            ),
            "requires_continuation_approval": False,
            "continuation_status": None,
            "continuation_request_id": None,
            "continuation_routed_to": None,
        })
    out.sort(key=lambda r: (
        _LIFECYCLE_ORDER.get(WorkItemLifecycle(r["lifecycle"]), 9),
        r["due_date"],
    ))

    overdue_lumpsum_ids = {
        r["work_item_id"] for r in out
        if r["work_item_id"] in lumpsum_ids and r["lifecycle"] == WorkItemLifecycle.overdue.value
    }
    if overdue_lumpsum_ids:
        from app.modules.continuation_requests.service import latest_requests_by_work_item

        latest = latest_requests_by_work_item(db, overdue_lumpsum_ids)
        for r in out:
            if r["work_item_id"] not in overdue_lumpsum_ids:
                continue
            req = latest.get(r["work_item_id"])
            if req is None:
                r["requires_continuation_approval"] = True
                continue
            r["continuation_request_id"] = req.id
            r["continuation_status"] = req.status
            r["requires_continuation_approval"] = req.status != "approved"
            r["continuation_routed_to"] = req.routed_to_name
    return out
```

Add the missing import at the top of `work_items.py` (it currently imports `ActivityMaster` already at line 25 — only `is_lumpsum_unit_row` needs adding, done inline above via a local import to avoid widening the module-level import surface for a Phase-2-only helper; this matches this file's existing lazy-import style for `continuation_requests.service`).

- [ ] **Step 5: Extend `OpenTaskOut`**

In `backend/app/modules/work_reports/schemas.py`, in `OpenTaskOut` (currently ending with `days_overdue: int = 0`), add:

```python
    lifecycle: str
    days_overdue: int = 0
    # Lump-sum continuation approval (Phase 2). Always False/None for a
    # TASK_WITH_QUANTITY item — only a lump-sum (NON_QUANTITATIVE) activity can
    # require approval to continue past its allowed duration.
    requires_continuation_approval: bool = False
    continuation_status: str | None = None
    continuation_request_id: uuid.UUID | None = None
    continuation_routed_to: str | None = None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest tests/test_continuation_requests.py -v`
Expected: PASS (all tests green). If `test_reassigned_head_takes_over_review_authority` or `test_self_approval_blocked` fail on the 403 assertion, check that `authz.can_review_report`/`reviewable_project_ids` are being called with the correct actor — these are pre-existing, already-tested helpers and should need no changes.

Run: `docker exec wms-backend-1 pytest tests/test_task_continuation.py -v`
Expected: PASS — no regression in the existing continuation suite (the gate only fires for `is_lumpsum_task=True` rows on a genuinely new LINK past due_date; every existing test either isn't lump-sum, isn't overdue at the point it links, or is a resave).

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/continuation_requests/service.py backend/app/modules/work_reports/work_items.py backend/app/modules/work_reports/schemas.py backend/tests/test_continuation_requests.py
git commit -m "feat(continuation-requests): approval gate on the lump-sum continuation engine"
```

---

## Task 6: Router + registration

**Files:**
- Create: `backend/app/modules/continuation_requests/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_continuation_requests.py` (extend)

**Interfaces:**
- Consumes: every function from `continuation_requests/service.py` (Task 5).
- Produces: the 6 live `/continuation-requests` endpoints the tests in Task 5 already exercise, plus the standalone read-endpoint tests added here.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_continuation_requests.py`:

```python
def test_employee_can_read_own_request_head_and_pm_can_too(flag_on, client, db, author, pm_header,
                                                            make_user, make_employee, login):
    a = author()
    head_u = make_user("head5@x.com", role=UserRole.employee)
    head = make_employee(employee_code="H5", user_id=head_u.id)
    a["project"].head_employee_id = head.id
    db.add(a["project"])
    db.commit()
    head_header = login("head5@x.com")

    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    assert client.get(f"{CR}/{req['id']}", headers=a["header"]).status_code == 200
    assert client.get(f"{CR}/{req['id']}", headers=head_header).status_code == 200
    assert client.get(f"{CR}/{req['id']}", headers=pm_header).status_code == 200


def test_stranger_cannot_read_request(flag_on, client, author, pm_header, make_user, login):
    a = author()
    _, sub = _lumpsum_sub(client, pm_header, period=1)
    wi = _start_work_item(client, a["header"], project_id=a["project"].id, sub_id=sub["id"], on_date=TODAY)
    next_day = TODAY + timedelta(days=1)
    req = client.post(CR, headers=a["header"], json={
        "work_item_id": wi, "continuation_date": next_day.isoformat(),
    }).json()

    make_user("stranger2@x.com", role=UserRole.employee)
    stranger = login("stranger2@x.com")
    res = client.get(f"{CR}/{req['id']}", headers=stranger)
    assert res.status_code == 403, res.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec wms-backend-1 pytest tests/test_continuation_requests.py -v`
Expected: FAIL with `404` for every `/continuation-requests` call — the router isn't mounted yet.

- [ ] **Step 3: Implement the router**

Create `backend/app/modules/continuation_requests/router.py`:

```python
"""Continuation-request endpoints (Lump-sum Activity Continuation Approval).

  POST  /continuation-requests                employee — request approval to continue
  GET   /continuation-requests/pending        PM / Project Head — pending queue
  GET   /continuation-requests                PM / Project Head — history (All Requests)
  GET   /continuation-requests/{id}           employee (own) or PM / Project Head
  POST  /continuation-requests/{id}/approve   PM / Project Head
  POST  /continuation-requests/{id}/reject    PM / Project Head

`/pending` is registered before `/{request_id}` so it is never swallowed by
the dynamic path (same ordering convention as activity_requests' `/mine` and
`/pending-count`).
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.continuation_requests import service
from app.modules.continuation_requests.schemas import (
    ContinuationRequestCreate,
    ContinuationRequestOut,
    ContinuationRequestPage,
    ContinuationReviewBody,
)
from app.modules.users.models import User

router = APIRouter(prefix="/continuation-requests", tags=["continuation-requests"])


@router.post("", response_model=ContinuationRequestOut, status_code=201)
def create_continuation_request(
    body: ContinuationRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.create_continuation_request(db, current, body)
    )


@router.get("/pending", response_model=list[ContinuationRequestOut])
def list_pending_continuation_requests(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContinuationRequestOut]:
    return [ContinuationRequestOut.model_validate(r) for r in service.list_pending(db, current)]


@router.get("", response_model=ContinuationRequestPage)
def list_continuation_requests(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestPage:
    rows, total = service.list_all(db, current, status=status, limit=limit, offset=offset)
    return ContinuationRequestPage(
        items=[ContinuationRequestOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{request_id}", response_model=ContinuationRequestOut)
def get_continuation_request(
    request_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.get_continuation_request(db, current, request_id)
    )


@router.post("/{request_id}/approve", response_model=ContinuationRequestOut)
def approve_continuation_request(
    request_id: uuid.UUID,
    body: ContinuationReviewBody,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.approve_continuation_request(db, current, request_id, body.comment)
    )


@router.post("/{request_id}/reject", response_model=ContinuationRequestOut)
def reject_continuation_request(
    request_id: uuid.UUID,
    body: ContinuationReviewBody,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.reject_continuation_request(db, current, request_id, body.comment)
    )
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add the import near the other module router imports (next to `from app.modules.activity_requests.router import router as activity_requests_router`):

```python
from app.modules.continuation_requests.router import router as continuation_requests_router
```

And add the registration line next to `app.include_router(activity_requests_router, prefix=settings.API_V1_PREFIX)`:

```python
    app.include_router(continuation_requests_router, prefix=settings.API_V1_PREFIX)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker exec wms-backend-1 pytest tests/test_continuation_requests.py -v`
Expected: PASS — full file green (every test from Task 5 and this task).

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/continuation_requests/router.py backend/app/main.py backend/tests/test_continuation_requests.py
git commit -m "feat(continuation-requests): mount the API router"
```

---

## Task 7: Full backend regression pass

**Files:** none (verification-only task).

- [ ] **Step 1: Run the full backend test suite**

Run: `docker exec wms-backend-1 pytest -q`
Expected: PASS. Pay particular attention to:
- `tests/test_leave_api.py` — the leave-to-Head workflow this plan must not touch.
- `tests/test_task_continuation.py` — pre-existing continuation behaviour (start/link/complete/cycle-confinement/reader-dedup).
- `tests/test_benchmark_exception.py`, `tests/test_benchmark_pending_export.py`, `tests/test_lumpsum_count_field.py` — TASK_STATUS_ONLY/TASK_WITH_QUANTITY export behaviour, unaffected by the new gate (which only blocks a save, never changes what's exported).
- `tests/test_work_reports_api.py:382` — the `openapi.json` smoke-check; confirm the new `/continuation-requests` paths appear without breaking existing schema assertions.

If any pre-existing test fails, treat it as a real regression from this plan's changes (most likely a due-date assertion that happened to depend on calendar-day math on a date that now differs under working-day math) — fix the test's fixture dates or the assertion, never silence the failure. Do not proceed to Task 8 until this run is fully green.

- [ ] **Step 2: Type/lint check (if configured)**

Run: `docker exec wms-backend-1 python -m mypy app/modules/continuation_requests app/modules/work_reports/work_items.py app/modules/calendar/working_days.py` (only if the repo has mypy configured — check for `mypy.ini`/`pyproject.toml` `[tool.mypy]` first; skip this step if not configured, do not add mypy configuration as part of this plan).

Expected: no new type errors introduced by this plan's files.

- [ ] **Step 3: No commit for this task** — it is a verification gate only.

---

## Task 8: Regenerate OpenAPI types for the frontend

**Files:**
- Modify: `frontend/openapi.json` (regenerated snapshot)
- Modify: `frontend/src/types/openapi.ts` (regenerated)

**Interfaces:**
- Produces: `components["schemas"]["ContinuationRequestOut"]`, `["ContinuationRequestCreate"]`, `["ContinuationReviewBody"]`, `["ContinuationRequestPage"]`, and the 4 new fields on `["OpenTaskOut"]` — consumed by every frontend task from here on.

- [ ] **Step 1: Snapshot the live backend spec**

With the backend container running (`ENABLE_API_DOCS=true` is already set in `backend/.env`):

Run: `curl -s http://localhost:8100/api/v1/openapi.json -o frontend/openapi.json`
Expected: the file is overwritten; `grep -c continuation-requests frontend/openapi.json` returns a non-zero count.

- [ ] **Step 2: Regenerate the TypeScript types**

Run: `cd frontend && npm run gen:api`
Expected: `src/types/openapi.ts` is regenerated; `grep -c ContinuationRequestOut frontend/src/types/openapi.ts` returns a non-zero count.

- [ ] **Step 3: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS (no existing code references the new schemas yet, so this should be a clean no-op check at this point — it only confirms the regeneration itself didn't break anything).

- [ ] **Step 4: Commit**

```bash
git add frontend/openapi.json frontend/src/types/openapi.ts
git commit -m "chore(api-types): regenerate from continuation-requests backend contract"
```

---

## Task 9: `continuation-requests` frontend feature module

**Files:**
- Create: `frontend/src/features/continuation-requests/types.ts`
- Create: `frontend/src/features/continuation-requests/api.ts`
- Create: `frontend/src/features/continuation-requests/keys.ts`
- Create: `frontend/src/features/continuation-requests/hooks.ts`
- Create: `frontend/src/features/continuation-requests/components/continuation-status-badge.tsx`
- Create: `frontend/src/features/continuation-requests/components/continuation-review-panel.tsx`
- Create: `frontend/src/features/continuation-requests/components/all-continuation-requests-list.tsx`
- Create: `frontend/src/features/continuation-requests/components/continuation-management-panel.tsx`
- Create: `frontend/src/features/continuation-requests/components/continuation-detail.tsx`
- Create: `frontend/src/features/continuation-requests/components/continuation-approval-card.tsx`
- Create: `frontend/src/app/(app)/attendance/continuation/[id]/page.tsx`

**Interfaces:**
- Consumes: `components["schemas"]["ContinuationRequestOut"|"ContinuationRequestPage"]` (Task 8), `workReportKeys` (`@/features/work-reports/keys`), `OpenTask` (`@/features/work-reports/types`).
- Produces: `ContinuationManagementPanel` (consumed by Task 10's attendance tab), `ContinuationApprovalCard` (consumed by Task 13), `usePendingContinuationRequests`/`useCreateContinuationRequest`/etc. (consumed by Tasks 10, 11, 13).

This module has no backend logic to test — it is verified visually in Task 14 (manual run-through) and by the frontend typecheck. Each step below is "write the file, then typecheck."

- [ ] **Step 1: `types.ts`**

```typescript
export type ContinuationRequestStatus = "pending" | "approved" | "rejected";

export interface ContinuationRequest {
  id: string;
  employee_id: string;
  work_item_id: string;
  project_id: string;
  sub_activity_id: string;
  original_report_date: string;
  allowed_duration_days: number;
  due_date: string;
  continuation_date: string;
  status: ContinuationRequestStatus;
  requested_at: string;
  reviewer_id: string | null;
  decision_comment: string | null;
  decided_at: string | null;
  employee_name: string;
  project_name: string;
  project_code: string;
  activity_name: string | null;
  sub_activity_name: string;
  reviewer_name: string | null;
  routed_to_name: string | null;
  routed_to_role: "head" | "manager" | null;
}

export interface ContinuationRequestPage {
  items: ContinuationRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContinuationRequestCreateBody {
  work_item_id: string;
  continuation_date: string;
}

export interface ContinuationReviewBody {
  comment?: string | null;
}

export interface ContinuationRequestListParams {
  status?: ContinuationRequestStatus | "";
  limit: number;
  offset: number;
}

export const CONTINUATION_STATUS_LABEL: Record<ContinuationRequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
};
```

- [ ] **Step 2: `api.ts`**

```typescript
import { api } from "@/lib/api-client";

import type {
  ContinuationRequest,
  ContinuationRequestCreateBody,
  ContinuationRequestListParams,
  ContinuationRequestPage,
  ContinuationReviewBody,
} from "./types";

function toQuery(p: ContinuationRequestListParams): string {
  const sp = new URLSearchParams();
  if (p.status) sp.set("status", p.status);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const continuationRequestsApi = {
  create: (body: ContinuationRequestCreateBody) =>
    api.post<ContinuationRequest>("/continuation-requests", body),
  pending: () => api.get<ContinuationRequest[]>("/continuation-requests/pending"),
  list: (params: ContinuationRequestListParams) =>
    api.get<ContinuationRequestPage>(`/continuation-requests?${toQuery(params)}`),
  get: (id: string) => api.get<ContinuationRequest>(`/continuation-requests/${id}`),
  approve: (id: string, body: ContinuationReviewBody) =>
    api.post<ContinuationRequest>(`/continuation-requests/${id}/approve`, body),
  reject: (id: string, body: ContinuationReviewBody) =>
    api.post<ContinuationRequest>(`/continuation-requests/${id}/reject`, body),
};
```

- [ ] **Step 3: `keys.ts`**

```typescript
import type { ContinuationRequestListParams } from "./types";

export const continuationRequestKeys = {
  all: ["continuation-requests"] as const,
  pending: () => [...continuationRequestKeys.all, "pending"] as const,
  list: (params: ContinuationRequestListParams) =>
    [...continuationRequestKeys.all, "list", params] as const,
  detail: (id: string) => [...continuationRequestKeys.all, "detail", id] as const,
};
```

- [ ] **Step 4: `hooks.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { workReportKeys } from "@/features/work-reports/keys";

import { continuationRequestsApi } from "./api";
import { continuationRequestKeys } from "./keys";
import type {
  ContinuationRequestCreateBody,
  ContinuationRequestListParams,
  ContinuationReviewBody,
} from "./types";

export function usePendingContinuationRequests(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: continuationRequestKeys.pending(),
    queryFn: () => continuationRequestsApi.pending(),
    enabled: options?.enabled ?? true,
  });
}

export function useContinuationRequestList(
  params: ContinuationRequestListParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: continuationRequestKeys.list(params),
    queryFn: () => continuationRequestsApi.list(params),
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
}

export function useContinuationRequest(id: string) {
  return useQuery({
    queryKey: continuationRequestKeys.detail(id),
    queryFn: () => continuationRequestsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ContinuationRequestCreateBody) => continuationRequestsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: continuationRequestKeys.all });
      // The employee's "Open tasks" card must flip to the new pending state.
      qc.invalidateQueries({ queryKey: workReportKeys.all });
    },
  });
}

export function useApproveContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ContinuationReviewBody }) =>
      continuationRequestsApi.approve(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: continuationRequestKeys.all }),
  });
}

export function useRejectContinuationRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ContinuationReviewBody }) =>
      continuationRequestsApi.reject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: continuationRequestKeys.all }),
  });
}
```

- [ ] **Step 5: `components/continuation-status-badge.tsx`**

```typescript
import { Badge } from "@/components/ui/badge";

import { CONTINUATION_STATUS_LABEL } from "../types";
import type { ContinuationRequestStatus } from "../types";

const VARIANT: Record<ContinuationRequestStatus, "neutral" | "success" | "warning" | "danger"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
};

export function ContinuationStatusBadge({ status }: { status: ContinuationRequestStatus }) {
  return <Badge variant={VARIANT[status] ?? "neutral"}>{CONTINUATION_STATUS_LABEL[status] ?? status}</Badge>;
}
```

- [ ] **Step 6: `components/continuation-review-panel.tsx`**

Pending Requests table with inline approve/reject — clones `leave-review-panel.tsx`'s exact interaction pattern (expandable row, optional comment `Textarea`, Confirm/Cancel).

```typescript
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";

import {
  useApproveContinuationRequest,
  usePendingContinuationRequests,
  useRejectContinuationRequest,
} from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

const COL_COUNT = 9;

export function ContinuationReviewPanel() {
  const router = useRouter();
  const pendingQuery = usePendingContinuationRequests();
  const approve = useApproveContinuationRequest();
  const reject = useRejectContinuationRequest();
  const pending = pendingQuery.data ?? [];

  const [action, setAction] = React.useState<{ id: string; type: "approve" | "reject" } | null>(null);
  const [comment, setComment] = React.useState("");
  const busy = approve.isPending || reject.isPending;

  function startAction(id: string, type: "approve" | "reject") {
    setAction({ id, type });
    setComment("");
  }

  function cancelAction() {
    setAction(null);
    setComment("");
  }

  async function confirmAction() {
    if (!action) return;
    const { id, type } = action;
    try {
      if (type === "approve") {
        await approve.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Continuation approved");
      } else {
        await reject.mutateAsync({ id, body: { comment: comment || null } });
        toast.success("Continuation rejected");
      }
      cancelAction();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : `Could not ${type} the request.`);
    }
  }

  if (pendingQuery.isLoading) return <TableSkeleton rows={3} cols={COL_COUNT} />;

  return (
    <Card>
      <CardHeader className="border-b border-border px-5 py-3.5">
        <CardTitle className="text-base flex items-center gap-2">
          Pending requests
          {pending.length > 0 && (
            <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-semibold text-warning">
              {pending.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {pending.length === 0 ? (
          <div className="px-5 py-8">
            <EmptyState
              title="No pending requests"
              description="All continuation requests have been reviewed."
            />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Activity</TableHead>
                <TableHead>Sub-Activity</TableHead>
                <TableHead>Original Date</TableHead>
                <TableHead>Allowed Duration</TableHead>
                <TableHead>Continuation Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((req) => (
                <React.Fragment key={req.id}>
                  <TableRow
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => router.push(`/attendance/continuation/${req.id}`)}
                  >
                    <TableCell className="font-medium">{req.employee_name}</TableCell>
                    <TableCell>{req.project_code || req.project_name}</TableCell>
                    <TableCell>{req.activity_name ?? "—"}</TableCell>
                    <TableCell>{req.sub_activity_name}</TableCell>
                    <TableCell className="tabular">{req.original_report_date}</TableCell>
                    <TableCell className="tabular">
                      {req.allowed_duration_days} {req.allowed_duration_days === 1 ? "day" : "days"}
                    </TableCell>
                    <TableCell className="tabular">{req.continuation_date}</TableCell>
                    <TableCell>
                      <ContinuationStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => startAction(req.id, "approve")}
                          disabled={busy}
                        >
                          <Check className="h-3.5 w-3.5" />
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => startAction(req.id, "reject")}
                          disabled={busy}
                        >
                          <X className="h-3.5 w-3.5" />
                          Reject
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>

                  {action?.id === req.id && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={COL_COUNT} className="bg-secondary/30 px-5 py-3">
                        <div className="flex items-start gap-2" onClick={(e) => e.stopPropagation()}>
                          <Textarea
                            className="text-sm"
                            rows={2}
                            placeholder={
                              action.type === "approve" ? "Note (optional)" : "Reason for rejection (optional)"
                            }
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                          />
                          <div className="flex flex-col gap-1 shrink-0">
                            <Button
                              size="sm"
                              variant={action.type === "approve" ? "secondary" : "danger"}
                              onClick={() => void confirmAction()}
                              loading={busy}
                            >
                              {action.type === "approve" ? "Confirm approve" : "Confirm reject"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={cancelAction}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 7: `components/all-continuation-requests-list.tsx`**

History table (no pagination — expected volume is low; add `Pagination` from `@/components/data/pagination`, matching `admin-leave-list.tsx`, only if real usage later shows more than one page is common).

```typescript
"use client";

import { EmptyState } from "@/components/feedback/empty-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useContinuationRequestList } from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

const LIMIT = 50;

export function AllContinuationRequestsList() {
  const query = useContinuationRequestList({ status: "", limit: LIMIT, offset: 0 });
  const items = query.data?.items ?? [];

  if (query.isLoading) return <TableSkeleton rows={5} cols={7} />;
  if (items.length === 0) {
    return <EmptyState title="No continuation requests" description="No requests have been filed yet." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Employee</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Activity</TableHead>
          <TableHead>Requested Date</TableHead>
          <TableHead>Decision Date</TableHead>
          <TableHead>Reviewer</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((req) => (
          <TableRow key={req.id}>
            <TableCell className="font-medium">{req.employee_name}</TableCell>
            <TableCell>{req.project_code || req.project_name}</TableCell>
            <TableCell>
              {req.activity_name ? `${req.activity_name} / ${req.sub_activity_name}` : req.sub_activity_name}
            </TableCell>
            <TableCell className="tabular">{req.requested_at.slice(0, 10)}</TableCell>
            <TableCell className="tabular">{req.decided_at ? req.decided_at.slice(0, 10) : "—"}</TableCell>
            <TableCell>{req.reviewer_name ?? "—"}</TableCell>
            <TableCell>
              <ContinuationStatusBadge status={req.status} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 8: `components/continuation-management-panel.tsx`**

```typescript
"use client";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { usePendingContinuationRequests } from "../hooks";
import { AllContinuationRequestsList } from "./all-continuation-requests-list";
import { ContinuationReviewPanel } from "./continuation-review-panel";

export function ContinuationManagementPanel() {
  const [queue, setQueue] = useUrlState("queue", "pending");
  const pendingCount = usePendingContinuationRequests().data?.length ?? 0;

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          {
            value: "pending",
            label: "Pending Requests",
            count: pendingCount || undefined,
            countVariant: "warning",
          },
          { value: "all", label: "All Requests" },
        ]}
        value={queue}
        onChange={setQueue}
      />
      {queue === "pending" && <ContinuationReviewPanel />}
      {queue === "all" && <AllContinuationRequestsList />}
    </div>
  );
}
```

- [ ] **Step 9: `components/continuation-detail.tsx`**

```typescript
"use client";

import type { ReactNode } from "react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useContinuationRequest } from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export function ContinuationDetail({ id }: { id: string }) {
  const query = useContinuationRequest(id);

  if (query.isLoading) {
    return (
      <>
        <PageHeader title="Continuation Request" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }
  if (query.isError || !query.data) {
    return (
      <>
        <PageHeader title="Continuation Request" />
        <ErrorState title="Could not load this request" />
      </>
    );
  }

  const req = query.data;
  return (
    <>
      <PageHeader
        title="Continuation Request"
        subtitle={`${req.employee_name} · ${req.project_code || req.project_name}`}
      />
      <Card>
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border px-5">
          <InfoRow label="Employee" value={req.employee_name} />
          <InfoRow label="Project" value={`${req.project_code || "—"} — ${req.project_name}`} />
          <InfoRow label="Activity" value={req.activity_name ?? "—"} />
          <InfoRow label="Sub-Activity" value={req.sub_activity_name} />
          <InfoRow label="Original Report" value={req.original_report_date} />
          <InfoRow
            label="Allowed Duration"
            value={`${req.allowed_duration_days} ${req.allowed_duration_days === 1 ? "day" : "days"}`}
          />
          <InfoRow label="Continuation Date" value={req.continuation_date} />
          <InfoRow
            label="Routed To"
            value={
              req.routed_to_name
                ? `${req.routed_to_name} (${req.routed_to_role === "head" ? "Project Head" : "Manager"})`
                : "—"
            }
          />
          <InfoRow label="Status" value={<ContinuationStatusBadge status={req.status} />} />
          {req.reviewer_name && <InfoRow label="Reviewer" value={req.reviewer_name} />}
          {req.decision_comment && <InfoRow label="Decision Comment" value={req.decision_comment} />}
        </CardContent>
      </Card>
    </>
  );
}
```

- [ ] **Step 10: the detail route**

Create `frontend/src/app/(app)/attendance/continuation/[id]/page.tsx`:

```typescript
"use client";

import { useParams } from "next/navigation";

import { ContinuationDetail } from "@/features/continuation-requests/components/continuation-detail";

export default function ContinuationDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <ContinuationDetail id={id} />;
}
```

- [ ] **Step 11: `components/continuation-approval-card.tsx`**

The employee-facing card, consumed by Task 13. Not wired into the app yet in this task — purely creates the component.

```typescript
"use client";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { OpenTask } from "@/features/work-reports/types";
import { AppError } from "@/lib/api-client";

import { useCreateContinuationRequest } from "../hooks";
import type { ContinuationRequestStatus } from "../types";
import { ContinuationStatusBadge } from "./continuation-status-badge";

interface Props {
  task: OpenTask;
  reportDate: string;
  onContinue: () => void;
}

export function ContinuationApprovalCard({ task, reportDate, onContinue }: Props) {
  const createRequest = useCreateContinuationRequest();
  const status = (task.continuation_status ?? null) as ContinuationRequestStatus | null;

  async function requestApproval() {
    try {
      await createRequest.mutateAsync({
        work_item_id: task.work_item_id,
        continuation_date: reportDate,
      });
      toast.success("Continuation approval requested");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not submit the request.");
    }
  }

  if (status === "approved") {
    return (
      <div className="space-y-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm">
        <p className="font-medium text-success">✓ Continuation approved</p>
        <Button type="button" size="sm" variant="secondary" onClick={onContinue}>
          Continue in today&apos;s report
        </Button>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm">
        <p className="font-medium text-danger">✕ Continuation rejected</p>
        <p className="mt-1 text-xs text-muted-foreground">
          You cannot continue this activity. Contact your Project Head for details.
        </p>
      </div>
    );
  }

  if (status === "pending") {
    return (
      <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
        <p className="font-medium">Continuation Approval Pending</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {task.continuation_routed_to
            ? `Your request has been sent to: ${task.continuation_routed_to}`
            : "Your request has been sent for review."}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          You cannot continue this activity until it is approved.
        </p>
        <div className="mt-1">
          <ContinuationStatusBadge status="pending" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
      <p className="font-medium">Continuation approval required</p>
      <p className="text-xs text-muted-foreground">
        This activity&apos;s allowed duration ({task.target_days} {task.target_days === 1 ? "day" : "days"}) has
        passed. You need Project Head approval before continuing.
      </p>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={() => void requestApproval()}
        loading={createRequest.isPending}
      >
        Request Continuation Approval
      </Button>
    </div>
  );
}
```

- [ ] **Step 12: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS. Fix any import-path mismatches against the real `@/components/ui/*` exports (`Badge`, `Button`, `Card`/`CardHeader`/`CardTitle`/`CardContent`, `Table*`, `Textarea`, `Skeleton`, `Tabs`) — these are the exact same imports `leave-review-panel.tsx`/`leave-detail.tsx`/`leave-management-panel.tsx` already use successfully.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/features/continuation-requests frontend/src/app/\(app\)/attendance/continuation
git commit -m "feat(continuation-requests): frontend feature module (Head review UI)"
```

---

## Task 10: Head-only "Lump-sum Activity Requests" tab on `/attendance`

**Files:**
- Modify: `frontend/src/features/attendance/tabs.ts`
- Modify: `frontend/src/features/attendance/components/attendance-view.tsx`

**Interfaces:**
- Consumes: `ContinuationManagementPanel` (Task 9), `useReportScope` (existing, `@/features/work-reports/hooks`).
- Produces: `?tab=lump-sum-activity` as a valid, deep-linkable tab value — consumed by Task 11's dashboard shortcut.

- [ ] **Step 1: Extend `tabs.ts`**

In `frontend/src/features/attendance/tabs.ts`, change the `TabKey` union:

```typescript
export type TabKey =
  | "calendar"
  | "history"
  | "leave"
  | "leave-balance"
  | "corrections"
  | "holidays"
  | "lump-sum-activity";
```

Add a field to `TabOptions`:

```typescript
export interface TabOptions {
  /** `attendance.manage` - gates the Leave Balance maintenance view. */
  canManage: boolean;
  /** `features.attendanceCorrections`, deferred until automated capture exists. */
  correctionsEnabled: boolean;
  /** PM (global reviewer) or Project Head — gates the "Lump-sum Activity
   *  Requests" tab, same authority as Leave's Team-approvals view. */
  canReviewContinuations: boolean;
}
```

Update `attendanceTabs` to accept and use the new option, inserting the tab right after Leave/Leave Balance (before Corrections/Holidays):

```typescript
export function attendanceTabs(
  { canManage, correctionsEnabled, canReviewContinuations }: TabOptions,
): TabItem[] {
  return [
    { value: "calendar", label: "Calendar" },
    // Records is the PM's daily review of the whole roster, so it is
    // manager-only: an employee has no business reading everyone else's day.
    // Their own attendance lives on the Calendar tab.
    ...(canManage ? ([{ value: "history", label: "Records" }] as TabItem[]) : []),
    { value: "leave", label: "Leave" },
    // Leave Balance is a manager/admin-only maintenance view.
    ...(canManage ? ([{ value: "leave-balance", label: "Leave Balance" }] as TabItem[]) : []),
    // Lump-sum Activity Requests — reviewer-only (PM or Project Head), same
    // authority model as Leave's Team-approvals view.
    ...(canReviewContinuations
      ? ([{ value: "lump-sum-activity", label: "Lump-sum Activity Requests" }] as TabItem[])
      : []),
    // Corrections is deferred until biometric / automated attendance capture
    // exists (attendance is entered manually today). Hidden behind a feature
    // flag; see features.attendanceCorrections.
    ...(correctionsEnabled ? ([{ value: "corrections", label: "Corrections" }] as TabItem[]) : []),
    { value: "holidays", label: "Holidays" },
  ];
}
```

`allowedTabKeys`/`resolveTab` need no changes — both are already derived purely from `attendanceTabs(options)`.

- [ ] **Step 2: Wire it into `attendance-view.tsx`**

In `frontend/src/features/attendance/components/attendance-view.tsx`, add the import (next to the existing `LeaveTab` import):

```typescript
import { ContinuationManagementPanel } from "@/features/continuation-requests/components/continuation-management-panel";
import { useReportScope } from "@/features/work-reports/hooks";
```

Inside `AttendanceView`, right after the existing `canRequestLeave` line, add the Head-scope resolution (mirrors `LeaveTab`'s own `useReportScope` call exactly, so a Head sees the tab without a second round-trip pattern being invented):

```typescript
  const { role, employeeId } = useAuth();
  const canManage = can(role, "attendance.manage");
  const canRequestLeave = Boolean(employeeId) && can(role, "leave.request");
  // Project-Head-ness for the Lump-sum Activity Requests tab — same
  // useReportScope call LeaveTab already makes for the same fact.
  const { data: scope } = useReportScope({ enabled: role !== "project_manager" });
  const isProjectHead = role !== "project_manager" && scope?.is_project_head === true;
  const canReviewContinuations = role === "project_manager" || isProjectHead;
```

Update the `tabOptions` object:

```typescript
  const tabOptions = {
    canManage,
    correctionsEnabled: features.attendanceCorrections,
    canReviewContinuations,
  };
```

Add the render branch, right after the existing `{tab === "leave" && <LeaveTab />}` line:

```typescript
      {tab === "leave" && <LeaveTab />}
      {tab === "lump-sum-activity" && canReviewContinuations && <ContinuationManagementPanel />}
```

(The `canReviewContinuations` re-check at render time, mirroring the existing `tab === "history" && canManage` pattern two lines below, guards against a hand-typed `?tab=lump-sum-activity` URL reaching the panel for an unauthorized viewer — `resolveTab` already prevents the tab strip itself from offering it, but this is the same belt-and-suspenders the codebase already applies to Records.)

- [ ] **Step 3: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/attendance/tabs.ts frontend/src/features/attendance/components/attendance-view.tsx
git commit -m "feat(attendance): add Head-only Lump-sum Activity Requests tab"
```

---

## Task 11: Head dashboard shortcut

**Files:**
- Modify: `frontend/src/features/dashboard/employee-dashboard.tsx`

**Interfaces:**
- Consumes: `usePendingContinuationRequests` (Task 9).

- [ ] **Step 1: Implement**

In `frontend/src/features/dashboard/employee-dashboard.tsx`, add the import (next to the existing `useLeaveList` import):

```typescript
import { Clock } from "lucide-react"; // add to the existing lucide-react import line
import { usePendingContinuationRequests } from "@/features/continuation-requests/hooks";
```

(`Clock` should be added to the existing `import { ArrowRight, CalendarOff, FileText, Plus } from "lucide-react";` line rather than as a second lucide import — i.e. that line becomes `import { ArrowRight, CalendarClock, CalendarOff, FileText, Plus } from "lucide-react";`, using `CalendarClock` to stay visually distinct from the plain `Clock` already used elsewhere for a different meaning.)

Right after the existing `pendingLeaveCount` line, add:

```typescript
  const pendingContinuations = usePendingContinuationRequests({ enabled: isProjectHead });
  const pendingContinuationCount = pendingContinuations.data?.length ?? 0;
```

Add the shortcut card right after the existing "Pending leave requests" button block (same `isProjectHead` gate, same visual pattern):

```typescript
              {isProjectHead && (
                <Button asChild className="justify-start" variant="secondary">
                  <Link href="/attendance?tab=lump-sum-activity&queue=pending">
                    <CalendarClock className="h-4 w-4" /> Lump-sum Activity Requests
                    {pendingContinuationCount > 0 && (
                      <Badge variant="warning" className="ml-auto">
                        {pendingContinuationCount}
                      </Badge>
                    )}
                  </Link>
                </Button>
              )}
```

- [ ] **Step 2: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/dashboard/employee-dashboard.tsx
git commit -m "feat(dashboard): add Lump-sum Activity Requests shortcut for Project Heads"
```

---

## Task 12: Notification types + icons

**Files:**
- Modify: `frontend/src/features/notifications/types.ts`
- Modify: `frontend/src/features/notifications/components/notification-item.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NotificationType` literals `"continuation_requested" | "continuation_approved" | "continuation_rejected"`, rendered correctly by the bell/dropdown/list already built (Task 5's backend already sends these exact type strings via `create_notification`).

- [ ] **Step 1: Extend `types.ts`**

In `frontend/src/features/notifications/types.ts`, add the three new literals to the `NotificationType` union (after `leave_cancelled`, before `report_submitted`, keeping the leave/report/continuation groupings together):

```typescript
export type NotificationType =
  | "leave_submitted"
  | "leave_approved"
  | "leave_rejected"
  | "leave_cancelled"
  | "continuation_requested"
  | "continuation_approved"
  | "continuation_rejected"
  | "report_submitted"
  | "report_approved"
  | "report_rejected"
  | "project_assigned"
  | "calendar_event_created"
  | "employee_created"
  // Ongoing-condition notifications (upserted/resolved, not one-off events).
  | "NUMERIC_BENCHMARK"
  | "TASK_OVERDUE"
  | "SYSTEM";
```

- [ ] **Step 2: Extend `notification-item.tsx`**

In `frontend/src/features/notifications/components/notification-item.tsx`, add `Clock3` to the existing lucide-react import (it already imports `Clock` for `TASK_OVERDUE`, distinct from a new icon needed here — use `UserCheck` and `UserX` for the two decision outcomes, `FileText` is already imported and reused for the request-created case):

```typescript
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  CheckCircle,
  ClipboardList,
  Clock,
  FileText,
  FolderKanban,
  UserCheck,
  UserPlus,
  UserX,
  X,
  XCircle,
} from "lucide-react";
```

Add three entries to `TYPE_CONFIG` (after `leave_cancelled`, mirroring its neighbours):

```typescript
  leave_cancelled:       { Icon: X,             color: "amber" },
  continuation_requested: { Icon: FileText,     color: "blue" },
  continuation_approved:  { Icon: UserCheck,    color: "green" },
  continuation_rejected:  { Icon: UserX,        color: "red" },
  report_submitted:      { Icon: FileText,      color: "blue" },
```

- [ ] **Step 3: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/notifications/types.ts frontend/src/features/notifications/components/notification-item.tsx
git commit -m "feat(notifications): add continuation-request notification types"
```

---

## Task 13: Employee-side "Continuation approval required" UI

**Files:**
- Modify: `frontend/src/features/work-reports/components/work-report-form.tsx`
- Modify: `frontend/src/features/work-reports/components/period-activity-editor.tsx`

**Interfaces:**
- Consumes: `ContinuationApprovalCard` (Task 9), `OpenTask.requires_continuation_approval`/`continuation_status`/`continuation_routed_to` (Task 8's regenerated types).

- [ ] **Step 1: Branch the "Open tasks" card in `work-report-form.tsx`**

In `frontend/src/features/work-reports/components/work-report-form.tsx`, add the import:

```typescript
import { ContinuationApprovalCard } from "@/features/continuation-requests/components/continuation-approval-card";
```

Replace the card body inside the `{openTasks.map((t) => ( ... ))}` block (currently ending with the plain `<Button onClick={() => continueTask(t)}>Continue in today's report</Button>`): keep everything above the button (the header row with project/activity names and the lifecycle badge, and the started/due date row) unchanged, and replace only the trailing `<Button ...>Continue in today's report</Button>` with a branch:

```typescript
                      {t.requires_continuation_approval ? (
                        <ContinuationApprovalCard
                          task={t}
                          reportDate={reportDate}
                          onContinue={() => continueTask(t)}
                        />
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="self-start"
                          onClick={() => continueTask(t)}
                        >
                          <ArrowRight className="h-4 w-4" />
                          Continue in today&apos;s report
                        </Button>
                      )}
```

(`reportDate` is already an in-scope form field value at this point in the component — it is the same `reportDate` passed to `useOpenTasks(reportDate, ...)` a few dozen lines above.)

- [ ] **Step 2: Disable the per-row "Continue existing task" prompt when gated**

In `frontend/src/features/work-reports/components/period-activity-editor.tsx`, inside the "Manual pick matched an open work item" block (the `{rowOpenMatch && !startNewRows.has(index) && ( ... )}` JSX, currently rendering "Continue existing task" / "Start a new task" buttons unconditionally), change the "Continue existing task" button to respect the gate:

```typescript
            {rowOpenMatch && !startNewRows.has(index) && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-sm">
                <span className="text-muted-foreground">
                  You have an open task for this activity (started{" "}
                  {rowOpenMatch.started_on}, due {rowOpenMatch.due_date}).
                  {rowOpenMatch.requires_continuation_approval && (
                    <> This task needs Project Head approval before it can be continued — see the card above.</>
                  )}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => attachToRow(index, rowOpenMatch)}
                    disabled={rowOpenMatch.requires_continuation_approval}
                  >
                    Continue existing task
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setStartNewRows((prev) => new Set(prev).add(index))
                    }
                  >
                    Start a new task
                  </Button>
                </div>
              </div>
            )}
```

(This is UI-only defense in depth — the real block is the backend gate from Task 5, Step 4. Even if a row bypassed this and called `attachToRow` directly, submitting the report would still 403 server-side.)

- [ ] **Step 3: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/work-reports/components/work-report-form.tsx frontend/src/features/work-reports/components/period-activity-editor.tsx
git commit -m "feat(work-reports): show continuation-approval-required state on gated tasks"
```

---

## Task 14: Manual verification + final regression

**Files:** none (verification-only task).

- [ ] **Step 1: Backend full suite**

Run: `docker exec wms-backend-1 pytest -q`
Expected: 100% pass, including every file touched by this plan and every pre-existing suite (leave, benchmarks, activity requests, work reports).

- [ ] **Step 2: Frontend typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS with zero errors across the whole project (not just the new files — a signature change to `OpenTask` or `NotificationType` can surface errors elsewhere).

- [ ] **Step 3: Manual run-through (dev environment)**

With both containers running:

1. As a PM, create a lump-sum sub-activity (`TASK_STATUS_ONLY`, `benchmark_period_days=1`) and assign a Project Head to a test project.
2. As an employee on that project, submit a work report today selecting that sub-activity (starts a `WorkItem`).
3. Submit a second report the next working day WITHOUT selecting "Continue existing task" first — confirm the "Open tasks from previous reports" card shows "Continuation approval required" with Project/Activity/Sub-Activity/Original Report/Allowed Duration/Continuation date, and a "Request Continuation Approval" button.
4. Click it; confirm the card flips to "Continuation Approval Pending" showing who it's routed to, and that no further report row can be created against that work item (the per-row prompt's "Continue existing task" is disabled too).
5. As the Project Head, open `/attendance?tab=lump-sum-activity`; confirm the request appears in Pending Requests with the dashboard shortcut count matching.
6. Approve it (with an optional comment). Confirm: it disappears from Pending, appears in All Requests as Approved, the employee receives an in-app notification, and the employee's card now shows "✓ Continuation approved" with a working "Continue in today's report" button that actually saves.
7. Repeat steps 2–5 with a second work item and Reject instead; confirm the employee sees "✕ Continuation rejected" and still cannot continue.
8. As an unrelated employee (not PM, not the project's Head), confirm `GET /continuation-requests/pending` and the detail page both refuse/redirect appropriately, and that hitting the approve/reject endpoints directly (e.g. via the browser devtools network tab replaying the request with a different session) returns 403.
9. Reassign the project's Head to a different employee mid-flow on a fresh pending request; confirm the old Head can no longer approve it and the new Head can.
10. Confirm a `TASK_WITH_QUANTITY` activity's continuation still behaves exactly as before this plan (no approval card ever appears, continuation is never blocked).

Report each step's actual outcome — do not claim success without having actually run it.

- [ ] **Step 4: No commit for this task** — it is a verification gate only. If any step in Step 3 fails, return to the relevant task, fix it, re-run that task's own tests, then re-run this task's Step 1–3 from the top.

---

## Self-Review

**1. Spec coverage** — every locked decision (1–20) and UI requirement from the user's approval message maps to a task:
- Decisions 1–2 (reuse engine, add gate on top): Task 5, Step 4.
- Decision 3 (NON_QUANTITATIVE = existing `TASK_STATUS_ONLY`, no new enum): Task 3, Task 5 (`is_lumpsum_unit_row`, no schema/enum changes anywhere).
- Decision 4 (`TASK_WITH_QUANTITY` unaffected): Task 3 (`is_lumpsum_task` flag), Task 5 (gate keyed off it), Task 5's `test_task_with_quantity_continuation_never_gated`.
- Decision 5 (flip `TASK_CONTINUATION_ENABLED`): Task 2, Step 5.
- Decision 6 (working-day due dates): Task 1, Task 2.
- Decision 7 (continuation state machine): Task 5's five gate/decision tests.
- Decision 8 (server-side enforcement): Task 5, Step 4 (the gate lives in `resolve_task_work_item`, not the frontend).
- Decision 9 (dedicated table): Task 4.
- Decision 10 (tied to WorkItem): `ContinuationRequest.work_item_id`, Task 4.
- Decision 11 (audit fields): `ContinuationRequest` columns, Task 4.
- Decision 12 (duplicate prevention): partial unique index (Task 4) + idempotent `create_continuation_request` (Task 5) + `test_duplicate_pending_request_returns_existing`.
- Decisions 13–14 (authz reuse, no frozen Head id): Task 5's `_assert_can_review`/`_notify_reviewer`/`_attach_names`, all resolving `authz.project_head_employee_id` fresh; `test_reassigned_head_takes_over_review_authority`.
- Decision 15 (PM-fallback = line manager): `_notify_reviewer`'s manager branch, Task 5; `test_no_head_falls_back_to_manager_and_pm_can_still_approve`.
- Decision 16 (self-approval blocked): `_assert_can_review`'s self-check, Task 5; `test_self_approval_blocked`.
- Decisions 17–20 (notifications on create/approve/reject): `_push`/`_notify_reviewer`/`_notify_employee`, Task 5; three dedicated notification-assertion tests.
- Employee UI (required/pending/approved/rejected states): Task 9 Step 11, Task 13.
- Head Attendance tab + Pending/All + review row + detail page: Tasks 9–10.
- Dashboard shortcut: Task 11.
- In-app notification icons: Task 12.
- No email anywhere: no task touches `notifications`' delivery mechanism beyond `create_notification`, and no SMTP/email module is referenced.
- Testing checklist (20 items in the original spec message): items 1–20 map onto Task 5/6's test functions one-for-one (within-duration → `test_within_duration_continues_normally`; 1-day/2-day working-day math → Task 1/2's tests; weekend handling → `test_due_date_skips_weekend`/`test_add_working_days_skips_weekend`; duplicate prevention → `test_duplicate_pending_request_returns_existing`; Head routing/reassignment/fallback → the routing/authorization block; pending/approve/reject/unblock → the gate tests; unauthorized/self-approval → the two dedicated tests; notifications → the three notification tests; `TASK_WITH_QUANTITY`/existing-continuation/leave regressions → Task 7).
- Database/migration question: answered inline in the prior conversation turn and only Task 4's single migration is created, per the "do not create a migration without first explaining it" instruction already satisfied before this plan was written.

**2. Placeholder scan** — no `TBD`/`TODO`/"add appropriate handling" strings appear in any task; every code block is complete, runnable code, not a description of code.

**3. Type consistency** — `ContinuationRequestStatus`/`ContinuationRequestOut`/`ContinuationRequest` (frontend) all carry the same field names throughout (Task 4 → 5 → 6 → 9); `has_approved_continuation`/`latest_requests_by_work_item` signatures match their call sites in `work_items.py` (Task 5); `OpenTaskOut`'s four new fields match `OpenTask`'s usage in `ContinuationApprovalCard` and the per-row prompt (Task 5/8/9/13); `workReportKeys.all` (used in Task 9's `useCreateContinuationRequest`) matches the real export confirmed in `frontend/src/features/work-reports/keys.ts`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-25-ls-continuation-approval.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?

