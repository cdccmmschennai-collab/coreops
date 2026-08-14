# Attendance Policy - Open Decisions

Every number the biometric attendance calculation depends on. Confirmed items are
implemented as configuration, never as constants scattered through services.
Open items block the phase named in the last column - not the phases before it.

Last updated: 2026-08-14 (Phase 7 - see section 6).

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

---

## 6. Phase 7 - duration + classification (implemented 2026-08-14)

Read-only. No migration, no `attendance_records` write, no persistence of any
kind: `GET /biometric/daily-summary` computes these per request.

### What was decided (engineering, not policy)

| Decision | Choice | Why |
|---|---|---|
| Shift source of truth | `offices.shift_start` / `shift_end` / `timezone` / `break_minutes` (migration 0007), per employee via `employees.office_id` | Already exists and already holds 09:00 / 17:30 / Asia/Kolkata for Chennai. Phase 7 added no shift table and no second configuration path. |
| Fallback when `office_id` is NULL | `DEFAULT_SHIFT_START` / `DEFAULT_SHIFT_END` in `biometric/constants.py` - the ONLY place 09:00 / 17:30 is written in the backend | The column is nullable, so a fallback is unavoidable; duplicating the literal is not. Flagged per row as `shift_source: "default"` + reason `default_shift_assumed`, never presented as configuration. |
| Scheduled duration | `shift_end - shift_start` = **510 minutes** for Chennai | A window, not a "required duration". O-1 is still open, so nothing compares against an invented requirement. |
| Classification vocabulary | Its own 4 values: `present`, `incomplete`, `needs_review`, `no_record` | `AttendanceStatus` (present/absent/half_day/leave/holiday/weekend/comp_off) encodes a CAUSE. Biometric evidence has none - a 6h day may be half day, permission, early release or a missed punch. Borrowing that enum would turn a measurement into an HR decision. |
| Session model | ONE session: `last_out - first_in` | EasyTime reports no punch direction (see `punch-state-mapping.md`), so pairing middle punches would be a guess about which trips were lunch and which were exits. |
| Break deduction | **None** | O-2 is open. Deducting 30 minutes would change every day silently. `break_minutes` is displayed only. |
| Overtime | **Not computed** | Days over 510 minutes are `present`, nothing more. Overtime needs O-1 first. |
| Night / cross-midnight shifts | Refused, not wrapped | `shift_end <= shift_start` yields reason `unsupported_shift_window` and sends the day to review rather than inventing a next-day rollover. |
| Bad office timezone | Refused, not defaulted to UTC | Reading a contracted 09:00 as UTC would move it by 5h30m for every day. Reason `shift_timezone_invalid`. |

### Still open, and now visible in the API

| # | Question | What Phase 7 does instead | Impact if answered |
|---|---|---|---|
| O-1 | Required daily working duration | Compares against the scheduled WINDOW (510m) | Would replace the comparison basis |
| O-2 | Does the 30m lunch count as worked time | No deduction | Every day changes by 30m |
| **O-3** | **Late-arrival grace period** | `SHORTFALL_GRACE_MINUTES = 0`. A day short of its window by even 1 minute is `needs_review` + `short_of_scheduled_duration` - never `half_day` | **One constant.** On the real 54-employee-day dataset, grace 0 already settles 44 days automatically because real days run longer than scheduled (average 9h 30m) |
| O-4 | Expected shift end | Uses `offices.shift_end` (17:30) | Would confirm or replace it |

`grace_minutes` is echoed on every response page so a consumer can see which
value produced the verdicts.

### Two discrepancies recorded rather than resolved

1. **Shift start: 08:30 vs 09:00.** Section 1 of this document lists 08:30 as
   confirmed by management, and warns that the office rows "may still hold the
   09:00 placeholder". The live rows hold **09:00** for all three offices, and
   09:00 - 17:30 is the baseline Phase 7 was specified against. Phase 7 reads
   configuration, so it currently computes against 09:00 / 510 minutes. If 08:30
   is correct, the fix is a data change to `offices.shift_start` (and the
   `DEFAULT_SHIFT_*` constants), not a code change - but it would make the
   scheduled window 540 minutes and move days between `present` and
   `needs_review`. **Needs confirmation before Phase 10.**
2. **Attendance day vs office timezone.** Phase 6 buckets the attendance day in
   `ATTENDANCE_TIMEZONE` (Asia/Kolkata) for every employee, while Phase 7 builds
   the scheduled window in the OFFICE's own timezone (per `offices/models.py`).
   For Chennai - every punch currently in the system - these agree. For the Qatar
   row (`Asia/Qatar`, 09:00 - 18:00) they would not, and "whose midnight starts an
   attendance day" is an unmade decision. Not blocking while the connector is
   single-office.
