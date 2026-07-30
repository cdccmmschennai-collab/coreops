# Attendance Policy - Open Decisions

Every number the biometric attendance calculation depends on. Confirmed items are
implemented as configuration, never as constants scattered through services.
Open items block the phase named in the last column - not the phases before it.

Last updated: 2026-07-29 (Phase 0/1).

---

## 1. Confirmed by management

| Item | Value | Note |
|---|---|---|
| Shift start | 08:30 | Start time, **not** a duration. Do not read it as "8h 30m required". |
| Lunch duration | 30 minutes | |
| Monthly permission entitlement | 240 minutes (4h) | Stored as integer minutes; never floating-point hours. |
| Permission carry-forward | None | Unused minutes expire at month end. |
| Approved permission | Counts as attendance credit | |
| Retrospective permission requests | Allowed | |
| Employee request/correction window | 7 calendar days | See open item O-9 - calendar vs working days. |
| Primary approver | Project Head | |
| Fallback approver | Project Manager | Also sees all requests and decisions. |
| Export authority | Project Manager only | Enforced in the backend, not just by hiding a button. |

Existing CoreOps data that already models part of this: `offices.shift_start`,
`offices.shift_end`, `offices.break_minutes`, `offices.timezone` (one row per
office, migration 0007). Phase 4 should extend that row rather than inventing a
second shift-configuration table.

Current office rows must be checked before Phase 4: `shift_start` may still hold
the 09:00 placeholder rather than the confirmed 08:30.

---

## 2. Open - blocking

| # | Question | Why it blocks | Blocks |
|---|---|---|---|
| O-1 | Required daily working duration (minutes) | Nothing can compute shortfall or overtime without it. `attendance/service.py` currently hard-codes `STANDARD_WORKDAY_MINUTES = 480` for the manual module - do not assume it carries over. | Phase 4 |
| O-2 | Does the 30-minute lunch count as worked time? | Changes every day's total by 30 minutes. | Phase 4 |
| O-3 | Late-arrival grace period | Determines the late/short-hours exception. | Phase 4 |
| O-4 | Expected shift end time | Needed for the "expected out" comparison. | Phase 4 |
| O-5 | Punch-state meaning | See `punch-state-mapping.md`. | Phase 3 |
| O-6 | EasyTime codes match CoreOps `employee_code` exactly | Determines how many `UNMAPPED_EMPLOYEE` exceptions day one produces. | Phase 2 |

---

## 3. Open - not blocking yet

| # | Question | Default until answered | Blocks |
|---|---|---|---|
| O-7 | New-employee permission entitlement | `MANUAL_ASSIGNMENT` - a PM sets the joining-month balance by hand. The other options (`NONE_FOR_JOINING_MONTH`, `FULL_ENTITLEMENT`, `PRORATED`, `AVAILABLE_AFTER_PROBATION`) are implemented as an enum so switching is a config change. | Phase 6 |
| O-8 | Permission during probation | Same as O-7. | Phase 6 |
| O-9 | "7 days" = calendar or working days? | Calendar days. | Phase 6/7 |
| O-10 | Custom permission durations, or only 1h/2h presets? | Presets, with a config switch to allow custom. | Phase 6 |
| O-11 | Must permission be requested in advance? | No - retrospective allowed within the window (confirmed above), so this only asks whether a *warning* is shown. | Phase 6 |
| O-12 | Official-duty credit rule | Approved official duty credits worked time and does **not** consume the personal permission balance. Kept configurable. | Phase 7 |
| O-13 | Daily finalization time | 02:00 the following day, `Asia/Kolkata`. | Phase 8 |
| O-14 | Do unresolved exceptions block the monthly export? | Not blocked; the export is visibly marked. Switchable. | Phase 9 |
| O-15 | Who is attendance administrator besides the PM? | PM only. CoreOps has exactly two global roles (`project_manager`, `employee`) plus per-project Head; a new global role is a larger change and should be avoided if PM suffices. | Phase 7 |
| O-16 | Project Head -> employee assignment confirmation | `projects.head_employee_id` (migration 0053) is the existing source of truth. Approver routing reads it. | Phase 6 |
| O-17 | PM fallback mapping | `employees.reporting_pm_id` exists and is the natural fallback. Confirm it is populated for all 25 imported employees. | Phase 6 |
| O-18 | Head/PM email addresses | `employees.work_email`; Brevo SMTP already in place. | Phase 6 |

---

## 4. Decisions taken in Phase 0/1 (not management's to make)

| Decision | Choice | Why |
|---|---|---|
| Raw punches immutable | Corrections never edit or delete a punch | Raw punches are audit evidence; corrections are separate approved records layered on top. |
| Durations in integer minutes | Everywhere, including the API and the ledger | Floating-point hours accumulate rounding error across a month. |
| Permission balance as a ledger | `permission_ledger` rows, not one mutable counter | Reconstructable, auditable, and a reversal is an entry rather than a subtraction. |
| Pending requests reserve balance | Reserved, not deducted | Prevents over-requesting without pretending unapproved time was granted. |
| Vendor code stored, meaning resolved server-side | Yes | A wrong mapping is fixed once, centrally, by recalculation. |
| Session engine is pure | No FastAPI, SQLAlchemy, HTTP or Excel imports | Makes every calculation rule directly unit-testable. |
| Biometric lives in its own module | Not merged into `modules/attendance` | The existing day-status CRUD must keep working untouched during shadow mode. |

---

## 5. Actual vs credited attendance

Kept as separate stored values, because they answer different questions
(payroll vs presence):

```
credited = actual_worked + approved_permission + approved_official_duty
shortfall = max(0, required - min(credited, required))
overtime  = max(0, actual_worked - required)      # from ACTUAL, never credited
```

Worked example (required 8h 30m, actual 5h 30m, permission 2h): credited 7h 30m,
shortfall 1h, overtime none.

The `required` value is O-1 and is still open.
