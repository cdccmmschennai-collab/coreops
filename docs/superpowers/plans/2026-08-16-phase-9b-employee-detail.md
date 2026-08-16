# Phase 9B — Employee Daily Attendance Detail + PM Decision Reflection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed root cause of PM decisions not appearing back in Records (the roster row's `first_in`/`last_out`/`worked_minutes` are computed from biometric evidence only, never merged with what the PM entered into `attendance_records`), then replace the Phase 9A detail-route stub with a real employee/day detail page: full punch list, merged evidence+decision summary, and the existing Phase 8 decision dialog wired to reflect immediately in Records and Calendar.

**Architecture:** One shared row-builder function (`_review_row`) replaces the inline per-employee block currently duplicated only once (inside `list_daily_review`'s loop) — extracting it lets a new single-employee detail service function call the exact same code, so the merge rule and every other row field are defined in exactly one place. The merge rule itself: device evidence always wins; a PM-entered `attendance_records.check_in_at`/`check_out_at` fills a boundary ONLY where the device recorded none. `classification`/`review_reasons`/`blocking_reasons` are untouched by this - they stay biometric-evidence-only, per the explicit spec requirement that "Biometric: No punch" must keep reading that way even after a PM sets the day Present. No new tables, no new columns, no migration - `attendance_records.note` (migration 0067) is reused as-is.

**Tech Stack:** FastAPI + SQLAlchemy (`backend/app/modules/biometric`), Next.js App Router + React Query + Tailwind (`frontend/src/features/biometric`, `frontend/src/features/attendance`).

**Spec:** Phase 9B instructions provided in-conversation (2026-08-16) — see conversation history for the full text; key excerpts are inlined per task below.

## Global Constraints

- Do not touch `biometric_punches` from any attendance write path. It already isn't touched (attendance and biometric are separate modules/tables) — no task may change that.
- Do not create a migration. `attendance_records.note` (migration 0067) is the only note column and is reused.
- Do not rename the Records status vocabulary (All/Present/Needs review/Punch missing/No punch) or reintroduce KPI cards / the old Record Attendance page / the old attendance-history table.
- Do not build an automatic leave-request → `attendance_records` sync, email notifications, overtime/break/session-pairing calculation, or a new biometric provider integration. (See Investigation summary — this does not exist today and is explicitly out of scope; "Leave" is set through the same generic decision flow this phase already fixes.)
- PM-only: reuse `require_role("project_manager")` / `RequireCapability capability="attendance.manage"` exactly as Phase 8/9A already do. Do not broaden permissions.
- Do not commit.

---

## Investigation summary (already done and empirically verified, informs every task below)

**Root cause, confirmed by reproduction** (`backend/tests/_diag_test.py`, run against the real service layer, then deleted): `service.list_daily_review`'s per-employee row sets `first_in`/`last_out`/`worked_minutes` from `verdict.first_in/last_out/worked_minutes` (`classify_day`'s output) **only**. `attendance_status`/`attendance_note`/`attendance_record_id` already correctly reflect a saved PM decision on the very next fetch (verified: creating an attendance record for a no-punch employee immediately shows `attendance_status: "present"`, `review_required: false` in the next `GET /biometric/daily-review` call — no caching bug, no stale-query bug). But `first_in`/`last_out`/`worked_minutes`/`classification` stay `None`/`None`/`None`/`"no_record"` even when the PM has entered `check_in_at`/`check_out_at` on that record (verified with `check_in_at=09:10`, `check_out_at=17:30`: the row still reported `first_in: null, last_out: null`). This is exactly what "Records must show First IN: 09:10 / Last OUT: 17:30" (spec section 14/15) requires and does not get today. **`classification` correctly must NOT change** (spec is explicit: "Biometric: No punch" stays) — only the merged display fields need fixing.
- Fix belongs entirely in the backend row-builder (`list_daily_review`'s per-employee block) — confirmed no frontend change is needed for Problem #1 itself, since `attendance-records.tsx` already binds directly to `r.first_in`/`r.last_out`/`r.worked_minutes`/`r.attendance_status` (built in Phase 9A). Fixing the source fixes the display automatically.
- **Calendar already reflects saved decisions correctly, with no code change needed.** Traced the full chain: `RecordDecisionDialog` → `useCreateAttendance`/`useUpdateAttendance` (`frontend/src/features/attendance/hooks.ts`) → `onSuccess: () => qc.invalidateQueries({queryKey: attendanceKeys.all})`. `attendanceKeys.all = ["attendance"]` and `attendanceKeys.list(...) = ["attendance", "list", params]` — React Query's default (non-exact) invalidation matches by prefix, so every `useAttendanceList` query (including the Calendar's) is invalidated by any create/update. `attendance-calendar.tsx`'s cell status is `record?.status ?? (holiday/weekend fallback)` — the **official** `attendance_records.status` already wins over everything else. This was already true before Phase 9B; verified by reading `attendance-calendar.tsx:227-235` and both `attendanceKeys.ts` files. No task in this plan touches the Calendar.
- **"Leave" is not automatically derived from approved leave requests today.** Traced `backend/app/modules/leave/service.py` end to end: `approve_leave_request`/`approve_leave_cancellation` only flip `LeaveRequest.status`; neither writes an `AttendanceRecord` row. `CalendarEventType` (`frontend/src/features/calendar/types.ts`) has no `"leave"` value either - it's holidays/working-day overrides only, unrelated to individual leave requests. So "Leave" on the Calendar is, today, **only** ever set the same way "Present" is: a PM explicitly choosing `status: "leave"` in the decision dialog (an existing, already-functional `AttendanceStatus` enum value - `present | absent | half_day | leave | holiday | weekend | comp_off`). Spec section 3 anticipates exactly this ("PM must be able to change/revoke the previous leave decision through the appropriate existing decision flow") and section 3/17/18 explicitly forbid building the missing automatic sync in this phase. **No backend or frontend change is needed for sections 3/17/18** beyond the general Problem #1 fix and detail page — a PM-set `leave` status already flows through the identical pipeline as `present`, already shows correctly on Records/Calendar, and is already re-editable (PATCH) to `present` once a real punch appears.
- "Permission" is not a value of `AttendanceStatus` at all (`present/absent/half_day/leave/holiday/weekend/comp_off`) — per spec's own "if supported by the existing model" hedge, nothing is added for it.
- `classify_day` (`backend/app/modules/biometric/classification.py:208`) already implements "two valid punches = Present regardless of duration" (management decision dated 2026-08-14, already in the codebase before this phase) - `REASON_SHORT_OF_SCHEDULED` is a non-blocking context reason, not a review trigger. Spec section 2 is already satisfied; no change needed.
- `can_set_check_in`/`can_set_check_out` (`verdict.first_in is None` / `verdict.last_out is None`) already correctly stay based on **device** evidence only, so a PM can keep editing their own previously-entered time (not device-locked) - no change needed to these flags.
- Device-punch immutability is structural, not enforced by application logic: nothing in `attendance/service.py` (create/update/delete) ever touches the `biometric_punches` table - it's a completely separate module/table, only ever written by `biometric/service.py`'s ingestion path. A regression test making this explicit is still worth adding (spec section 22 backend test 5).
- Records' "Reason" column currently always shows `primaryReason(r.blocking_reasons)` (the evidence gap, e.g. "No biometric record for this day") even once a PM has recorded an official reason in `attendance_note`. Spec section 4's example ("Reason: appropriate official decision reason") wants the PM's own note to win once one exists. Small, non-business-logic display-precedence fix in `attendance-records.tsx` (Task 4).

---

## Task 1: Backend — shared row-builder with the evidence/decision merge

**Files:**
- Modify: `backend/app/modules/biometric/constants.py`
- Modify: `backend/app/modules/biometric/service.py`
- Modify: `backend/app/modules/biometric/schemas.py`

**Interfaces:**
- Produces: `_review_row(*, employee_id, employee_code, employee_name, verdict, record) -> dict` - the single place `first_in`/`last_out`/`worked_minutes`/`first_in_source`/`last_out_source`/`review_required`/`can_set_check_in`/`can_set_check_out` are computed. Both `list_daily_review` (Task 1) and `get_daily_review_detail` (Task 2) call it.
- Consumes: `DayClassification` (from `classification.classify_day`, unchanged), `AttendanceRecord | None` (from `_official_records`, unchanged).

- [x] **Step 1: Add source/role vocabulary to `constants.py`**

Append to `backend/app/modules/biometric/constants.py`:

```python
# ── Phase 9B: PM decision reflection + detail page ──────────────────────────
# Whether a displayed IN/OUT boundary came from the device or was supplied by
# a PM where the device recorded none. Device evidence always wins - see
# service._merge_boundary. Biometric evidence itself is never written by a PM;
# this labels the DISPLAYED first_in/last_out only.
SOURCE_DEVICE = "device"
SOURCE_PM = "pm"

# The role a punch plays on the detail page's evidence list. Only the first
# and last surviving punch of the day carry a boundary role - intermediate
# punches are shown as context, never treated as a paired session (EasyTime
# reports no punch direction in this deployment; see summary.py).
PUNCH_ROLE_FIRST_IN = "first_in"
PUNCH_ROLE_LAST_OUT = "last_out"
PUNCH_ROLE_PUNCH = "punch"
```

- [x] **Step 2: Add `worked_minutes` to the classification import and extract `_review_row` + `_merge_boundary` in `service.py`**

Find the existing import from `classification` near the top of `backend/app/modules/biometric/service.py` (it already imports `Shift`, `classify_day`) and add `worked_minutes`:

```python
from app.modules.biometric.classification import Shift, classify_day, worked_minutes
```

(If the existing import line has a different exact set of names, add `worked_minutes` to whatever is already imported from that module - do not create a second import line.)

Add these two functions immediately before `list_daily_review` (which currently starts the "Phase 8: PM daily review" section):

```python
def _merge_boundary(
    device_value: datetime | None, pm_value: datetime | None
) -> tuple[datetime | None, str | None]:
    """Device evidence always wins. A PM-entered time fills a boundary the
    device did not record; a boundary the device DID record can never be
    displaced by a value copied from `attendance_records`, even if the two
    disagree. Returns (value, source), source is SOURCE_DEVICE / SOURCE_PM /
    None.
    """
    if device_value is not None:
        return device_value, SOURCE_DEVICE
    if pm_value is not None:
        return pm_value, SOURCE_PM
    return None, None


def _review_row(
    *,
    employee_id: uuid.UUID,
    employee_code: str | None,
    employee_name: str,
    verdict: DayClassification,
    record: AttendanceRecord | None,
) -> dict:
    """One employee-day, as both the roster view and the detail view need it.

    THE SINGLE PLACE the evidence/decision merge happens, so `list_daily_review`
    (one call per roster employee) and `get_daily_review_detail` (one call, one
    employee) can never drift apart on what "Records must show the saved
    decision" means.

    `classification`/`review_reasons`/`blocking_reasons` describe BIOMETRIC
    EVIDENCE ONLY and are never touched by a PM decision - a `no_record` day
    stays `no_record` even once the PM has entered a full day, because the
    device still saw nothing that day. `first_in`/`last_out`/`worked_minutes`
    are the DISPLAY boundary: the device's value first, the official record's
    value only where the device recorded none.
    """
    first_in, first_in_source = _merge_boundary(
        verdict.first_in, record.check_in_at if record else None
    )
    last_out, last_out_source = _merge_boundary(
        verdict.last_out, record.check_out_at if record else None
    )

    return {
        "employee_id": employee_id,
        "employee_code": employee_code,
        "employee_name": employee_name,
        "first_in": first_in,
        "last_out": last_out,
        "worked_minutes": worked_minutes(first_in, last_out),
        "first_in_source": first_in_source,
        "last_out_source": last_out_source,
        "scheduled_start_at": verdict.scheduled_start_at,
        "scheduled_end_at": verdict.scheduled_end_at,
        "scheduled_minutes": verdict.scheduled_minutes,
        # Evidence-only. See docstring above - never derived from `record`.
        "classification": verdict.classification,
        "review_required": verdict.review_required and record is None,
        # Biometric evidence is immutable and complete evidence cannot be
        # improved, so the PM may supply a time ONLY where the DEVICE (not the
        # official record) did not record one.
        "can_set_check_in": verdict.first_in is None,
        "can_set_check_out": verdict.last_out is None,
        "review_reasons": list(verdict.reasons),
        "blocking_reasons": [r for r in verdict.reasons if r in BLOCKING_REVIEW_REASONS],
        "attendance_record_id": record.id if record else None,
        "attendance_status": record.status.value if record else None,
        "attendance_check_in_at": record.check_in_at if record else None,
        "attendance_check_out_at": record.check_out_at if record else None,
        "attendance_note": record.note if record else None,
    }
```

- [x] **Step 3: Rewrite `list_daily_review`'s loop body to call `_review_row`**

Replace the loop body (from `for employee_id, employee_code, first_name, last_name in employees:` through the `items.append({...})` call) with:

```python
    for employee_id, employee_code, first_name, last_name in employees:
        times = punches.get(employee_id)
        # No punches is an ABSENCE OF EVIDENCE, represented in memory only. It is
        # never an absence from work and never a stored row.
        day_summary = summarize_day(times) if times else EMPTY_DAY
        verdict = classify_day(
            day_summary,
            day=on_date,
            shift=shifts.get(employee_id) or default_shift,
        )

        counts[verdict.classification] = counts.get(verdict.classification, 0) + 1
        record = official.get(employee_id)
        row = _review_row(
            employee_id=employee_id,
            employee_code=employee_code,
            employee_name=f"{first_name} {last_name}".strip(),
            verdict=verdict,
            record=record,
        )

        if row["review_required"]:
            review_required_count += 1

        if classification is not None and verdict.classification != classification:
            continue

        if normalized_q:
            name = row["employee_name"].lower()
            code = (employee_code or "").lower()
            if normalized_q not in name and normalized_q not in code:
                continue

        items.append(row)
```

The function's final `return {...}` block (review_date/provider/items/total/limit/offset/counts) is unchanged.

- [x] **Step 4: Add `first_in_source`/`last_out_source` to `DailyReviewRowOut`**

In `backend/app/modules/biometric/schemas.py`, in `DailyReviewRowOut` (in the "Phase 8: PM daily review" section), add two fields after `worked_minutes`:

```python
    first_in: datetime | None = None
    last_out: datetime | None = None
    worked_minutes: int | None = None
    # "device" | "pm" | null - which value this DISPLAYED boundary came from.
    # A PM-entered time only ever fills a boundary the device did not record;
    # see service._merge_boundary. Biometric evidence itself is unaffected.
    first_in_source: str | None = None
    last_out_source: str | None = None
```

- [x] **Step 5: Typecheck the module boundary by running the existing biometric tests**

Run: `docker exec wms-backend-1 pytest tests/test_biometric_daily_review.py tests/test_biometric_daily_summary.py tests/test_biometric_classification.py tests/test_biometric_mapping_admin.py -q`
Expected: PASS (the merge is additive - every existing row still has `first_in`/`last_out` equal to the device value whenever a device value exists, so no existing assertion should change).

---

## Task 2: Backend — single-employee detail endpoint

**Files:**
- Modify: `backend/app/modules/biometric/service.py`
- Modify: `backend/app/modules/biometric/schemas.py`
- Modify: `backend/app/modules/biometric/router.py`
- Test: `backend/tests/test_biometric_daily_review_detail.py` (new file)

**Interfaces:**
- Produces: `GET /biometric/daily-review/{employee_id}?date=YYYY-MM-DD` → `DailyReviewDetailOut { review_date, provider, row: DailyReviewRowOut, punches: list[PunchEntryOut] }`. PM-only, read-only.
- Consumes: `_review_row` (Task 1), `_punches_for_day` (extended to accept an optional employee filter), `_employee_shifts`, `_official_records` (all pre-existing).

- [x] **Step 1: Let `_punches_for_day` filter to one or more employees**

In `backend/app/modules/biometric/service.py`, change `_punches_for_day`'s signature and add one optional `WHERE` clause:

```python
def _punches_for_day(
    db: Session,
    *,
    provider: str,
    on_date: date,
    employee_ids: set[uuid.UUID] | None = None,
) -> dict[uuid.UUID, list[datetime]]:
```

In the `select(...)` call's `.where(...)`, add, right after the existing `local_day == on_date` clause:

```python
    conditions = [
        BiometricPunch.provider == provider,
        Employee.deleted_at.is_(None),
        local_day == on_date,
    ]
    if employee_ids is not None:
        conditions.append(Employee.id.in_(employee_ids))
    rows = db.execute(
        select(Employee.id, BiometricPunch.punch_time)
        .select_from(BiometricPunch)
        .join(
            BiometricEmployeeMapping,
            and_(
                BiometricEmployeeMapping.provider == BiometricPunch.provider,
                BiometricEmployeeMapping.external_employee_code
                == BiometricPunch.external_employee_code,
                BiometricEmployeeMapping.is_active.is_(True),
            ),
        )
        .join(Employee, Employee.id == BiometricEmployeeMapping.employee_id)
        .where(*conditions)
    ).all()
```

(Replace the existing `.where(BiometricPunch.provider == provider, Employee.deleted_at.is_(None), local_day == on_date)` call with the `conditions` list built above, passed as `.where(*conditions)`. `list_daily_review`'s existing call site - `_punches_for_day(db, provider=provider, on_date=on_date)` - needs no change; `employee_ids` defaults to `None`, so its query is byte-identical to today.)

- [x] **Step 2: Add `get_daily_review_detail` to `service.py`**

Add after `list_daily_review`:

```python
def get_daily_review_detail(
    db: Session, *, provider: str, on_date: date, employee_id: uuid.UUID
) -> dict:
    """One employee, one day - the Phase 9B PM detail screen.

    Calls the SAME per-row computation `list_daily_review` uses for every
    roster employee (`_review_row`), for exactly one, plus the full surviving
    punch list `DailyReviewRowOut` deliberately omits (see its docstring - it
    is evidence-narrow by design; this endpoint is where evidence inspection
    belongs). Read-only, exactly like the roster view: no attendance_records
    write, no punch touched, no synthetic punch invented.
    """
    employee = db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise AppError("not_found", "Employee not found.", 404)

    times = _punches_for_day(
        db, provider=provider, on_date=on_date, employee_ids={employee_id}
    ).get(employee_id) or []
    day_summary = summarize_day(times) if times else EMPTY_DAY
    shift = _employee_shifts(db, {employee_id}).get(employee_id) or Shift.default(
        timezone_name=settings.ATTENDANCE_TIMEZONE
    )
    verdict = classify_day(day_summary, day=on_date, shift=shift)
    record = _official_records(db, on_date=on_date, employee_ids={employee_id}).get(
        employee_id
    )

    row = _review_row(
        employee_id=employee.id,
        employee_code=employee.employee_code,
        employee_name=f"{employee.first_name} {employee.last_name}".strip(),
        verdict=verdict,
        record=record,
    )

    kept = day_summary.kept
    punches = []
    for i, punch_time in enumerate(kept):
        if i == 0:
            role = PUNCH_ROLE_FIRST_IN
        elif i == len(kept) - 1 and len(kept) >= 2:
            role = PUNCH_ROLE_LAST_OUT
        else:
            role = PUNCH_ROLE_PUNCH
        # Every row here comes straight from biometric_punches (via
        # summarize_day's dedup) - it is ALWAYS device evidence. A PM-entered
        # boundary lives only in `row` (attendance_check_in_at/out), never
        # here - see the module docstring: no synthetic punch is invented.
        punches.append({"punch_time": punch_time, "role": role, "source": SOURCE_DEVICE})

    return {
        "review_date": on_date,
        "provider": provider,
        "row": row,
        "punches": punches,
    }
```

Add the two new constant imports (`PUNCH_ROLE_FIRST_IN`, `PUNCH_ROLE_LAST_OUT`, `PUNCH_ROLE_PUNCH`, `SOURCE_DEVICE`) to the existing `from app.modules.biometric.constants import (...)` block at the top of `service.py`.

- [x] **Step 3: Add `PunchEntryOut` and `DailyReviewDetailOut` to `schemas.py`**

Add after `DailyReviewPage` in `backend/app/modules/biometric/schemas.py`:

```python
class PunchEntryOut(BaseModel):
    """One surviving (post-dedup) punch on the detail page's evidence list.

    Always `source="device"` - nothing here is ever PM-entered. A PM-supplied
    boundary the device did not record lives on `row.attendance_check_in_at` /
    `row.attendance_check_out_at`, never as a row in this list: no synthetic
    punch is invented (see the module docstring).
    """

    punch_time: datetime
    # first_in | last_out | punch. Only the first and last surviving punch of
    # the day carry a boundary role - see PUNCH_ROLE_* in constants.py.
    role: str
    source: str = "device"


class DailyReviewDetailOut(BaseModel):
    """One employee, one day - the Phase 9B PM detail screen.

    `row` is the exact same shape `DailyReviewPage.items` uses, so the two
    screens can never disagree about what a saved decision looks like.
    """

    review_date: date
    provider: str
    row: DailyReviewRowOut
    punches: list[PunchEntryOut]
```

- [x] **Step 4: Add the router endpoint**

In `backend/app/modules/biometric/router.py`, add the import `DailyReviewDetailOut` to the existing `from app.modules.biometric.schemas import (...)` block, and add this endpoint immediately after `list_daily_review`:

```python
@admin_router.get("/daily-review/{employee_id}", response_model=DailyReviewDetailOut)
def get_daily_review_detail(
    employee_id: uuid.UUID,
    review_date: date = Query(alias="date"),
    provider: str = Query(default=PROVIDER_EASYTIME),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> DailyReviewDetailOut:
    """One employee, one day - the Phase 9B PM detail screen.

    project_manager ONLY, exactly like `/daily-review`. Read-only: reports
    what the biometric evidence and the official record (if any) say; writes
    nothing.
    """
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            "validation_error",
            f"provider must be one of {sorted(SUPPORTED_PROVIDERS)}.",
            422,
        )
    today_local = datetime.now(ZoneInfo(settings.ATTENDANCE_TIMEZONE)).date()
    if review_date > today_local:
        raise AppError("validation_error", "Date must not be in the future.", 422)

    result = service.get_daily_review_detail(
        db, provider=normalized_provider, on_date=review_date, employee_id=employee_id
    )
    return DailyReviewDetailOut.model_validate(result)
```

- [x] **Step 5: Write the new backend test file**

Create `backend/tests/test_biometric_daily_review_detail.py`:

```python
"""Phase 9B - GET /biometric/daily-review/{employee_id}: the detail screen,
and the evidence/decision merge it shares with the roster view."""
from datetime import datetime, timezone

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.users.models import UserRole

DETAIL = "/api/v1/biometric/daily-review/{employee_id}"
REVIEW = "/api/v1/biometric/daily-review"
ATTEND = "/api/v1/attendance"
DAY = "2026-08-10"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-detail@x.com", role=UserRole.project_manager)


def _punch(db, employee, *, code: str, hour: int, minute: int = 0, n: int = 1):
    db.add(
        BiometricPunch(
            provider="easytime",
            external_transaction_id=f"txn-{code}-{hour}-{minute}-{n}",
            external_employee_code=code,
            employee_id=None,
            punch_time=datetime(2026, 8, 10, hour, minute, tzinfo=timezone.utc),
            received_at=datetime.now(timezone.utc),
            raw_punch_state="0",
        )
    )
    db.commit()


def _map(db, employee, *, code: str):
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee.id,
            is_active=True,
        )
    )
    db.commit()


def test_detail_returns_correct_employee_and_date(client, pm, db, make_employee):
    emp = make_employee(employee_code="D001", first_name="Kumar", last_name="Chandramouli")
    res = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review_date"] == DAY
    assert body["row"]["employee_id"] == str(emp.id)
    assert body["row"]["employee_name"] == "Kumar Chandramouli"
    assert body["punches"] == []


def test_unauthorized_user_cannot_read_detail(client, auth_header, make_employee):
    emp = make_employee(employee_code="D002", first_name="A", last_name="B")
    emp_header = auth_header("emp-detail@x.com", role=UserRole.employee)
    res = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=emp_header)
    assert res.status_code == 403


def test_no_punch_official_decision_is_persisted_and_reflected(client, pm, db, make_employee):
    emp = make_employee(employee_code="D003", first_name="No", last_name="Punch")

    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:10:00+05:30",
            "check_out_at": f"{DAY}T17:30:00+05:30",
            "note": "Biometric punch was missed.",
        },
    )
    assert create.status_code == 201, create.text

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = detail["row"]
    # Evidence stays "no_record" - the device saw nothing.
    assert row["classification"] == "no_record"
    # But the display boundary and the decision are both visible.
    assert row["attendance_status"] == "present"
    assert row["attendance_note"] == "Biometric punch was missed."
    assert row["first_in_source"] == "pm"
    assert row["last_out_source"] == "pm"
    assert row["first_in"] is not None
    assert row["last_out"] is not None
    assert row["worked_minutes"] == 8 * 60 + 20

    roster = client.get(REVIEW, params={"date": DAY}, headers=pm).json()
    roster_row = next(r for r in roster["items"] if r["employee_id"] == str(emp.id))
    assert roster_row == row


def test_missing_out_is_completed_and_in_stays_device(client, pm, db, make_employee):
    emp = make_employee(employee_code="D004", first_name="One", last_name="Punch")
    _map(db, emp, code="D004")
    _punch(db, emp, code="D004", hour=3, minute=35)  # 09:05 IST

    before = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert before["row"]["classification"] == "incomplete"
    assert before["row"]["can_set_check_in"] is False
    assert before["row"]["can_set_check_out"] is True
    assert before["row"]["first_in_source"] == "device"
    assert before["row"]["last_out_source"] is None

    update = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": before["row"]["first_in"],
            "check_out_at": f"{DAY}T17:30:00+05:30",
            "note": None,
        },
    )
    assert update.status_code == 201, update.text

    after = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = after["row"]
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "pm"
    assert row["first_in"] == before["row"]["first_in"]
    assert row["last_out"] is not None
    # Evidence is still "incomplete" - only one punch was ever seen.
    assert row["classification"] == "incomplete"
    assert row["attendance_status"] == "present"


def test_two_device_punches_are_present_and_locked(client, pm, db, make_employee):
    emp = make_employee(employee_code="D005", first_name="Two", last_name="Punch")
    _map(db, emp, code="D005")
    _punch(db, emp, code="D005", hour=3, minute=48)   # 09:18 IST
    _punch(db, emp, code="D005", hour=12, minute=7)   # 17:37 IST

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    row = detail["row"]
    assert row["classification"] == "present"
    assert row["review_required"] is False
    assert row["can_set_check_in"] is False
    assert row["can_set_check_out"] is False
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "device"
    assert len(detail["punches"]) == 2
    assert detail["punches"][0]["role"] == "first_in"
    assert detail["punches"][1]["role"] == "last_out"
    assert all(p["source"] == "device" for p in detail["punches"])


def test_intermediate_punches_are_visible_but_not_boundaries(client, pm, db, make_employee):
    emp = make_employee(employee_code="D006", first_name="Four", last_name="Punch")
    _map(db, emp, code="D006")
    _punch(db, emp, code="D006", hour=3, minute=35)   # 09:05
    _punch(db, emp, code="D006", hour=6, minute=45)   # 12:15
    _punch(db, emp, code="D006", hour=7, minute=30)   # 13:00
    _punch(db, emp, code="D006", hour=12, minute=2)   # 17:32

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    roles = [p["role"] for p in detail["punches"]]
    assert roles == ["first_in", "punch", "punch", "last_out"]
    assert len(detail["punches"]) == 4


def test_note_survives_reopening_and_editing(client, pm, db, make_employee):
    emp = make_employee(employee_code="D007", first_name="Note", last_name="Keeper")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "half_day",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Left early - doctor appointment.",
        },
    )
    record_id = create.json()["id"]

    reopened = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert reopened["row"]["attendance_note"] == "Left early - doctor appointment."

    # Editing status without resending note must not erase it.
    update = client.patch(
        f"{ATTEND}/{record_id}", headers=pm, json={"status": "present"}
    )
    assert update.status_code == 200, update.text
    assert update.json()["note"] == "Left early - doctor appointment."


def test_device_punches_are_never_modified_by_a_pm_decision(client, pm, db, make_employee):
    emp = make_employee(employee_code="D008", first_name="Immutable", last_name="Evidence")
    _map(db, emp, code="D008")
    _punch(db, emp, code="D008", hour=3, minute=35)  # 09:05, incomplete

    before_punches = sorted(
        (p.external_transaction_id, p.punch_time.isoformat())
        for p in db.query(BiometricPunch).filter_by(external_employee_code="D008").all()
    )

    client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:05:00+05:30",
            "check_out_at": f"{DAY}T17:45:00+05:30",
            "note": None,
        },
    )

    after_punches = sorted(
        (p.external_transaction_id, p.punch_time.isoformat())
        for p in db.query(BiometricPunch).filter_by(external_employee_code="D008").all()
    )
    assert before_punches == after_punches
    assert len(after_punches) == 1


def test_leave_status_flows_through_the_same_pipeline_as_present(client, pm, db, make_employee):
    """No automatic leave-request sync exists (see plan investigation summary) -
    this only proves the generic decision flow already carries `leave` through
    Records exactly like `present`, and can be revised once real evidence
    exists."""
    emp = make_employee(employee_code="D009", first_name="Leave", last_name="Day")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "leave",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Approved leave.",
        },
    )
    assert create.status_code == 201, create.text
    record_id = create.json()["id"]

    detail = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert detail["row"]["attendance_status"] == "leave"
    assert detail["row"]["review_required"] is False

    # The employee later punches in for real - biometric evidence appears, and
    # the PM can revise the decision through the same PATCH endpoint.
    _map(db, emp, code="D009")
    _punch(db, emp, code="D009", hour=3, minute=48)
    _punch(db, emp, code="D009", hour=12, minute=7)

    with_evidence = client.get(
        DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm
    ).json()
    assert with_evidence["row"]["classification"] == "present"
    assert with_evidence["row"]["attendance_status"] == "leave"  # still leave until PM acts

    resolved = client.patch(f"{ATTEND}/{record_id}", headers=pm, json={"status": "present"})
    assert resolved.status_code == 200, resolved.text

    final = client.get(DETAIL.format(employee_id=emp.id), params={"date": DAY}, headers=pm).json()
    assert final["row"]["attendance_status"] == "present"
```

- [x] **Step 6: Run the new test file and the full targeted biometric/attendance suite**

Run: `docker exec wms-backend-1 pytest tests/test_biometric_daily_review_detail.py -v`
Expected: all PASS.

Run: `docker exec wms-backend-1 pytest tests/test_biometric_daily_review.py tests/test_biometric_daily_review_detail.py tests/test_biometric_daily_summary.py tests/test_biometric_classification.py tests/test_biometric_mapping_admin.py tests/test_biometric_ingestion.py tests/test_biometric_migration.py tests/test_attendance.py -q`
Expected: all PASS, no regressions.

Run: `docker exec wms-backend-1 pytest -q`
Expected: same pre-existing unrelated failures as Phase 9A's report (work_reports, benchmarks, notifications, task_continuation, project_head, pending_export_regression), nothing new.

---

## Task 3: Frontend — types/api/hooks/keys for the detail endpoint

**Files:**
- Modify: `frontend/src/features/biometric/types.ts`
- Modify: `frontend/src/features/biometric/api.ts`
- Modify: `frontend/src/features/biometric/hooks.ts`
- Modify: `frontend/src/features/biometric/keys.ts`

**Interfaces:**
- Produces: `useDailyReviewDetail({ employeeId, date, enabled? })` returning `AttendanceDayDetail` - consumed by Task 4.

- [x] **Step 1: Extend `DailyReviewRow` and add the new types**

In `frontend/src/features/biometric/types.ts`, add two fields to `DailyReviewRow` (after `worked_minutes`):

```typescript
  first_in: string | null;
  last_out: string | null;
  worked_minutes: number | null;
  /** "device" | "pm" | null - which value this DISPLAYED boundary came from.
   *  A PM-entered time only ever fills a boundary the device did not record;
   *  biometric evidence itself is unaffected. */
  first_in_source: "device" | "pm" | null;
  last_out_source: "device" | "pm" | null;
```

Add two new interfaces after `DailyReviewPage`:

```typescript
export interface PunchEntry {
  punch_time: string;
  /** Only the first and last surviving punch of the day carry a boundary
   *  role; everything between is context, never a paired session. */
  role: "first_in" | "last_out" | "punch";
  /** Always "device" - a PM-entered boundary is never a punch row; see
   *  AttendanceDayDetail.row instead. */
  source: "device";
}

export interface AttendanceDayDetail {
  review_date: string;
  provider: string;
  row: DailyReviewRow;
  punches: PunchEntry[];
}
```

- [x] **Step 2: Add `getDailyReviewDetail` to `api.ts`**

In `frontend/src/features/biometric/api.ts`, add after `listDailyReview`:

```typescript
  /** One employee, one day - the Phase 9B PM detail screen. project_manager-
   *  only and strictly read-only. */
  getDailyReviewDetail: (params: {
    employeeId: string;
    date: string;
    provider?: string;
  }) => {
    const sp = new URLSearchParams({
      provider: params.provider ?? PROVIDER_EASYTIME,
      date: params.date,
    });
    return api.get<AttendanceDayDetail>(
      `${BASE}/daily-review/${params.employeeId}?${sp.toString()}`,
    );
  },
```

Add `AttendanceDayDetail` to the `import type { ... } from "./types"` block at the top of the file.

- [x] **Step 3: Add `useDailyReviewDetail` to `hooks.ts`**

In `frontend/src/features/biometric/hooks.ts`, add after `useDailyReview`:

```typescript
/** One employee, one day - the Phase 9B PM detail screen. */
export function useDailyReviewDetail(params: {
  employeeId: string;
  date: string;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: biometricKeys.dailyReviewDetail(params.employeeId, params.date),
    queryFn: () =>
      biometricApi.getDailyReviewDetail({
        employeeId: params.employeeId,
        date: params.date,
      }),
    enabled: params.enabled !== false && !!params.employeeId && !!params.date,
    staleTime: 60 * 1000,
  });
}
```

- [x] **Step 4: Add the key builder to `keys.ts`**

In `frontend/src/features/biometric/keys.ts`, add after `dailyReview`:

```typescript
  // Phase 9B detail screen: one employee, one day.
  dailyReviewDetail: (employeeId: string, date: string) =>
    [...biometricKeys.all, "daily-review-detail", employeeId, date] as const,
```

- [x] **Step 5: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS (this task only adds exports; nothing consumes them yet).

---

## Task 4: Frontend — the real detail page + Records reason precedence

**Files:**
- Modify: `frontend/src/app/(app)/attendance/records/[employeeId]/page.tsx` (replace the Phase 9A stub)
- Modify: `frontend/src/features/attendance/components/attendance-records.tsx` (one-line reason precedence fix)

**Interfaces:**
- Consumes: `useDailyReviewDetail` (Task 3), `RecordDecisionDialog` (existing, unchanged), `ATTENDANCE_STATUS_LABEL` (existing), `CLASSIFICATION_LABEL`/`CLASSIFICATION_VARIANT` (existing, from `review.ts`).
- Produces: nothing consumed elsewhere.

- [x] **Step 1: Replace the stub detail page**

Replace the entire contents of `frontend/src/app/(app)/attendance/records/[employeeId]/page.tsx`:

```tsx
"use client";

import { Suspense } from "react";
import * as React from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil } from "lucide-react";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { nowInIST } from "@/lib/ist";

import { biometricKeys } from "@/features/biometric/keys";
import { useDailyReviewDetail } from "@/features/biometric/hooks";
import { formatISTTime } from "@/features/biometric/mapping-format";
import {
  CLASSIFICATION_LABEL,
  CLASSIFICATION_VARIANT,
  EMPTY,
  formatReviewDate,
  formatWorked,
} from "@/features/biometric/review";
import type { PunchEntry } from "@/features/biometric/types";

import { RecordDecisionDialog } from "@/features/attendance/components/record-decision-dialog";
import { ATTENDANCE_STATUS_LABEL } from "@/features/attendance/schemas";
import type { AttendanceStatus } from "@/features/attendance/types";

const PUNCH_ROLE_LABEL: Record<PunchEntry["role"], string> = {
  first_in: "First IN",
  last_out: "Last OUT",
  punch: "Punch",
};

/** Today's date in Asia/Kolkata as `YYYY-MM-DD`. Mirrors attendance-records.tsx -
 *  never a UTC date, since at 02:00 IST the UTC date is still yesterday. */
function isoInIST(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Phase 9B: the PM's daily attendance detail for one employee, one day.
 *
 * Reached only from a Records row click (`attendance-records.tsx`), which
 * always supplies `?date=`; a direct/deep link without one falls back to
 * today rather than rendering blank. Editing reuses `RecordDecisionDialog`
 * unchanged - the same Phase 8 dialog Records itself uses - so there is one
 * decision UI, not two.
 */
function AttendanceRecordDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const today = React.useMemo(() => isoInIST(nowInIST()), []);

  const rawDate = searchParams.get("date");
  const date = rawDate && /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : today;

  const [editing, setEditing] = React.useState(false);

  const query = useDailyReviewDetail({ employeeId, date });
  const row = query.data?.row;
  const punches = query.data?.punches ?? [];

  const backHref = `/attendance?tab=history&date=${date}`;

  return (
    <RequireCapability capability="attendance.manage">
      <Link
        href={backHref}
        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Records
      </Link>

      {query.isLoading && (
        <div className="mt-4 space-y-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {query.isError && (
        <ErrorState
          message="Could not load this employee's attendance for this day."
          onRetry={() => void query.refetch()}
        />
      )}

      {row && (
        <>
          <PageHeader
            className="mt-2"
            title={row.employee_name || "Attendance detail"}
            subtitle={`${row.employee_code ?? ""}${row.employee_code ? " · " : ""}${formatReviewDate(date)}`}
            actions={
              <div className="flex items-center gap-2">
                {row.attendance_status ? (
                  <Badge variant="outline">
                    {ATTENDANCE_STATUS_LABEL[row.attendance_status as AttendanceStatus] ??
                      row.attendance_status}
                  </Badge>
                ) : (
                  <Badge variant="neutral">No decision yet</Badge>
                )}
                <Button size="sm" onClick={() => setEditing(true)}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
              </div>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="border-b border-border px-5 py-3.5">
                <CardTitle className="text-base">Attendance summary</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-4 pt-5 text-sm">
                <SummaryField label="First IN" value={row.first_in ? formatISTTime(row.first_in) : EMPTY} />
                <SummaryField label="Last OUT" value={row.last_out ? formatISTTime(row.last_out) : EMPTY} />
                <SummaryField label="Worked" value={formatWorked(row.worked_minutes)} />
                <div className="col-span-3 border-t border-border pt-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Source
                  </p>
                  <p className="mt-0.5 text-sm">{boundarySourceLabel(row)}</p>
                </div>
                <div className="col-span-3">
                  <Badge variant={CLASSIFICATION_VARIANT[row.classification]} dot>
                    {CLASSIFICATION_LABEL[row.classification]}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-border px-5 py-3.5">
                <CardTitle className="text-base">Official attendance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-5 text-sm">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Status
                  </p>
                  <p className="mt-0.5">
                    {row.attendance_status
                      ? (ATTENDANCE_STATUS_LABEL[row.attendance_status as AttendanceStatus] ??
                        row.attendance_status)
                      : "No decision yet"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Reason
                  </p>
                  <p className="mt-0.5 whitespace-pre-line text-muted-foreground">
                    {row.attendance_note?.trim() || "No reason given."}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Decision source
                  </p>
                  <p className="mt-0.5">
                    {row.attendance_status === "leave"
                      ? "Leave"
                      : row.attendance_record_id
                        ? "PM decision"
                        : "Not yet decided"}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader className="border-b border-border px-5 py-3.5">
              <CardTitle className="text-base">Biometric punches</CardTitle>
            </CardHeader>
            <CardContent className="pt-5">
              {punches.length === 0 ? (
                <EmptyState
                  title="No punch"
                  description="The biometric device recorded nothing for this employee on this day."
                />
              ) : (
                <ul className="divide-y divide-border">
                  {punches.map((p, i) => (
                    <li
                      key={`${p.punch_time}-${i}`}
                      className="flex items-center justify-between py-2 text-sm"
                    >
                      <span className="tabular font-medium">
                        {formatISTTime(p.punch_time)}
                      </span>
                      <span className="text-muted-foreground">
                        {PUNCH_ROLE_LABEL[p.role]}
                      </span>
                      <Badge variant="neutral">Device</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}

      <RecordDecisionDialog
        row={editing ? (row ?? null) : null}
        date={date}
        onClose={() => {
          setEditing(false);
          // The saved decision changes this employee's row on both the
          // detail screen and the Records roster (a different query) - and
          // the Calendar's official-status source (attendanceKeys, already
          // invalidated by the mutation itself). Invalidating every
          // biometric query here is the same broad pattern the mapping tab
          // already uses (useInvalidateCodes) for the same reason: the
          // active detail query refetches immediately, and the roster query
          // refetches the next time Records is observed.
          void queryClient.invalidateQueries({ queryKey: biometricKeys.all });
        }}
      />
    </RequireCapability>
  );
}

function SummaryField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="tabular mt-0.5 text-base font-semibold">{value}</p>
    </div>
  );
}

/** "Biometric" when both boundaries are device evidence, "PM entered" when
 *  both were supplied by hand, "Biometric + PM entered" when mixed, or a
 *  plain dash when nothing exists yet for either boundary. */
function boundarySourceLabel(row: {
  first_in_source: "device" | "pm" | null;
  last_out_source: "device" | "pm" | null;
}): string {
  const sources = new Set([row.first_in_source, row.last_out_source].filter(Boolean));
  if (sources.size === 0) return EMPTY;
  if (sources.has("device") && sources.has("pm")) return "Biometric + PM entered";
  if (sources.has("device")) return "Biometric";
  return "PM entered";
}

export default function AttendanceRecordDetailPage() {
  return (
    <Suspense>
      <AttendanceRecordDetail />
    </Suspense>
  );
}
```

- [x] **Step 2: Records "Reason" column prefers the PM's note once a decision exists**

In `frontend/src/features/attendance/components/attendance-records.tsx`, find:

```tsx
                    <TableCell className="text-sm text-muted-foreground">
                      {reason ?? EMPTY}
                    </TableCell>
```

Replace with:

```tsx
                    <TableCell className="text-sm text-muted-foreground">
                      {/* Once a PM has decided the day, their stated reason is
                          the useful one to show - the evidence gap that used
                          to block review is no longer what the row is about. */}
                      {r.attendance_note?.trim() || reason || EMPTY}
                    </TableCell>
```

- [x] **Step 3: Typecheck**

Run: `docker exec wms-frontend-1 npm run typecheck`
Expected: PASS.

- [x] **Step 4: Build**

Run: `docker exec wms-frontend-1 npm run build`
Expected: PASS, `/attendance/records/[employeeId]` still listed as a dynamic route.

- [x] **Step 5: Manual verification with the dev server**

In a browser, signed in as a PM (or with test data seeded - coordinate with the user if no PM credentials exist in the dev DB, same limitation noted in the Phase 9A report):

1. From Records, click a two-punch employee's row → detail page shows employee/date correctly, First IN/Last OUT/Worked from the device, "Biometric" as source, `Present` badge, both punches listed and locked (no edit inputs shown as editable in the dialog once opened).
2. Click a no-punch employee's row → Biometric punches card shows the "No punch" empty state; Attendance summary shows dashes. Click Edit, enter IN 09:10 / OUT 17:30, status Present, a reason, Save. Detail page immediately shows First IN 09:10, Last OUT 17:30, source "PM entered", status Present, the reason.
3. Click "← Records" - the row for that employee now shows the same First IN/Last OUT/Status/Reason without a manual page refresh being required (React Query refetches on the invalidated roster query when Records remounts).
4. Refresh the browser on the detail page directly (`/attendance/records/<id>?date=...`) - the same saved data reappears (not blank, not reset).
5. Open a one-punch employee, confirm the existing IN is disabled/locked in the edit dialog and only OUT is editable; save an OUT; confirm Records/detail both update.
6. Confirm Calendar (the signed-in PM's own, if they have an employee profile) still reflects any decision made for their own attendance date, unchanged from Phase 9A/Phase 8 behavior.
7. Confirm pagination (15/page) on Records is unaffected.
8. Confirm the words "Incomplete" and "Complete" still do not appear anywhere in the Records or detail UI (`Punch missing`/`Present` continue to be used).

---

## Self-review checklist (run after all tasks land)

- [x] Spec coverage: Problem #1 root cause (Task 1), detail page (Tasks 2-4), all punches visible (Task 2 Step 2 + Task 4 Step 1), device punches locked (unchanged `can_set_check_in`/`out`, tested in Task 2 Step 5), missing-punch completion (Task 1 merge + existing `RecordDecisionDialog`), official decision + reason/note (Task 4 Step 1, reusing migration 0067's `note`), Records refresh after save (Task 4 Step 1's `invalidateQueries`), Calendar reflection (verified already-working in the investigation summary, no task needed), PM-only auth (`require_manager`/`RequireCapability`, unchanged), leave boundary (verified already-working via the generic decision flow, documented, no task needed), database safety (no migration in any task).
- [x] No task inserts a synthetic row into `biometric_punches`, or writes anything outside `attendance_records` from the attendance write path.
- [x] `classification`/`review_reasons`/`blocking_reasons` are never computed from `record` (the official row) anywhere in `_review_row` - only `review_required` reads `record is None`, exactly as before.
- [x] Type consistency: `DailyReviewRow` (frontend) gains the same two fields (`first_in_source`, `last_out_source`) `DailyReviewRowOut` (backend) gains; `AttendanceDayDetail.row` is typed as the same `DailyReviewRow`, so `RecordDecisionDialog`'s existing `row: DailyReviewRow | null` prop accepts it with no adapter/cast.
