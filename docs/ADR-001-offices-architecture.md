# ADR-001 — Offices / Branch Architecture

**Status:** Accepted  
**Date:** 2026-06-03  
**Phase:** C3

---

## Context

CoreOps operates across multiple geographic locations (Chennai, Hyderabad, Qatar). Each location has
distinct shift timings, timezone rules, and break policies. Previously, location was captured as a
freeform enum on individual work reports (`work_location`), with no structured entity to hold
per-office configuration. This prevented any rule-based logic (shift compliance, overtime,
timezone-aware reminders) from being implemented without hardcoding.

---

## Decision

### 1. Offices are a first-class entity

An `offices` table stores each physical branch as a row. No office configuration is hardcoded in
application code. Future changes (new branch, updated shift times) require only a data change.

### 2. Timezone strategy

All timestamps stored in the database are UTC (`TIMESTAMPTZ`). The `timezone` column on `offices`
holds an IANA timezone string (e.g., `Asia/Kolkata`, `Asia/Qatar`). Conversion to local time is
done at presentation time using the employee's linked office timezone.

This avoids ambiguous "wall clock" timestamps in the DB and keeps arithmetic correct across DST
boundaries.

### 3. Shift times stored as local TIME values

`shift_start` and `shift_end` are stored as `TIME` (no timezone). They represent the local time at
that office. Combined with the `timezone` field, a specific UTC datetime can be computed for any
given date. Example: Chennai `shift_end = 17:30` in `Asia/Kolkata` → `12:00 UTC` on a standard day.

`break_minutes` stores the total unpaid break duration. Net work hours = shift duration − break.

### 4. Attendance calculation deferred

This ADR authorises the `offices` entity and `employees.office_id` FK only. Shift compliance
checks, overtime calculation, and timezone-aware reminder scheduling are explicitly deferred to a
later phase. The `offices` table provides the schema foundation; no attendance logic reads from it
yet.

### 5. Employee ↔ Office relationship

Each employee has one home office (`office_id` — nullable FK). Nullable allows:
- Existing employees to remain valid before assignment
- Contract/remote workers with no fixed office

Assignment is optional; downstream calculations guard on `office_id IS NOT NULL`.

### 6. `employee.office_id` vs `report.work_location`

| Field | Table | Meaning |
|---|---|---|
| `office_id` | `employees` | **Home office** — the branch the employee is permanently assigned to. Drives shift rules, timezone display, payroll, reminders. |
| `location` | `daily_work_reports` | **Where the employee physically worked that day** — can differ (e.g., travelling to Hyderabad while home-officed in Chennai). Informational; does not drive shift calculations. |

These are independent and intentionally separate.

### 7. Future branch expansion strategy

Adding a new office is a one-row INSERT into `offices`. No code changes required. Feature flags,
enum migrations, and deploys are not needed — the design is data-driven.

---

## Seeded Offices

| Name | Timezone | Shift Start | Shift End | Break | Active |
|---|---|---|---|---|---|
| Chennai | Asia/Kolkata | 09:00 | 17:30 | 30 min | ✓ |
| Hyderabad | Asia/Kolkata | 09:00 | 17:30 | 60 min | ✓ |
| Qatar | Asia/Qatar | 09:00 | 18:00 | 60 min | ✓ |

> **Note — Hyderabad shift end:** The office configuration provided listed `05:30` as the shift end
> for Hyderabad. This has been interpreted as `17:30` (5:30 PM) based on the 09:00 start and
> business context. Update `offices` row if the intended value differs.

---

## Consequences

**Positive**
- Office configuration is versioned and auditable (row history)
- Shift rules are extensible without deploys
- Timezone handling is unambiguous (UTC storage + IANA conversion)
- Attendance module can read `office_id` when ready

**Negative / Trade-offs**
- Employees without `office_id` will be excluded from future shift compliance reports until assigned
- Admin must assign office when creating employees (optional for now, required for future features)
