# V4 Attendance — Backend Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete, tested (83/83), OpenAPI + Swagger verified. **Implementation only — no frontend, no mock data.**

Mirrors the Employees and Projects modules exactly (FastAPI modular monolith, SQLAlchemy ORM, thin router → service layer, incremental Alembic, uniform error envelope, JWT/RBAC).

---

## 1. Files created / modified

**Created** `backend/app/modules/attendance/`:
- `models.py` — `AttendanceRecord` + `AttendanceStatus` enum
- `schemas.py` — `AttendanceOut/Create/Update/Page`
- `service.py` — RBAC-scoped reads + admin writes + minute calculation
- `router.py` — endpoints (+ employee-scoped sub-router)
- `alembic/versions/0004_attendance.py` — migration
- `tests/test_attendance.py` — 17 tests

**Modified:** `alembic/env.py` (import model), `app/main.py` (register both routers), `tests/conftest.py` (truncate `attendance_records`, add `make_attendance` fixture).

## 2. Database & migration

**Migration `0004_attendance`** (down-rev `0003_projects`; verified reversible up→down→up):
- `attendance_status` enum: `present, absent, half_day, leave, holiday, weekend`
- `attendance_records`:

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| employee_id | uuid → employees.id ON DELETE RESTRICT | |
| attendance_date | date | |
| check_in_at / check_out_at | timestamptz nullable | |
| total_minutes | int (default 0) | **derived** |
| overtime_minutes | int (default 0) | **derived** |
| status | attendance_status | |
| created_by/updated_by, created_at/updated_at | audit | |

Constraints: **UNIQUE(employee_id, attendance_date)** (duplicate prevention), CHECK minutes ≥ 0, CHECK `check_out_at >= check_in_at`. Indexes on `(employee_id, attendance_date)` and `(attendance_date)`.

> **Design note:** attendance is an operational log, so `DELETE` **hard-removes** the record (no soft-delete) and uniqueness is a plain `UNIQUE` — a deliberate, documented deviation from the soft-delete used by employees/projects (which the field list omitted).

## 3. Endpoints (`/api/v1`)

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/attendance` | any auth (scoped) | list + filters (`employee_id`, `status`, `from`, `to`) + pagination |
| POST | `/attendance` | **admin** | create (computes minutes, dup → 409) |
| GET | `/attendance/{id}` | any auth (scoped) | read one |
| PATCH | `/attendance/{id}` | **admin** | update (recomputes minutes) |
| DELETE | `/attendance/{id}` | **admin** | hard delete → 204 |
| GET | `/employees/{id}/attendance` | any auth (scoped) | one employee's attendance |

## 4. Service layer (logic, not just router)

- **RBAC enforced in the service:** admin = all · manager = **team** (`employees.manager_id = self`) · employee = **own** · viewer = all (read). Writes are admin-only (router gate + service sets audit actor).
- **`total_minutes`** = `(check_out − check_in)` in whole minutes (0 if either missing or negative).
- **`overtime_minutes`** = `max(0, total − 480)` (8-hour standard workday). Both are **server-derived** and read-only (not accepted on create/update).
- **Duplicate prevention:** `(employee_id, attendance_date)` checked in the service (→ 409) and backed by the DB unique constraint.
- **Validation:** employee must exist (→ 422); `check_out >= check_in` (→ 422).
- Scoped reads via `_current_employee` helper + a team subquery (reused from the employees module).

**Error mapping:** 401 · 403 (scope) · 404 · 409 (duplicate) · 422 (unknown employee / bad times).

## 5. Tests — 17 new, **83 total passing**

`docker compose run --rm --no-deps --entrypoint pytest backend -q` → `83 passed`.

- **CRUD + calc:** create computes 540 total / 60 overtime (09:00–18:00); no-times → 0/0; duplicate 409; unknown employee 422; check-out<check-in 422; update recomputes (→ 480/0); update status; delete → 204 then 404; unknown 404.
- **Filters:** pagination, status filter, date-range (`from`/`to`).
- **RBAC:** viewer read-but-not-create; employee sees only own; employee can't read other's record (403); manager sees team only + can't create (403); `/employees/{id}/attendance` scoped (own 200, other 403, admin any 200).

## 6. Verification

- **Tests:** 83/83 in the `python:3.12` container.
- **Migration:** applied + reversible; table/enum/constraints confirmed via `\d`.
- **OpenAPI (for frontend generation):** paths `/attendance`, `/attendance/{record_id}`, `/employees/{employee_id}/attendance`; schemas `AttendanceOut/Create/Update/Page`, `AttendanceStatus`.
- **Swagger UI:** `http://localhost:8100/api/v1/docs` → **200** (live, includes attendance).

## 7. Notes / decisions
- DELETE = hard delete (attendance log correction); plain unique on (employee, date).
- Minutes are derived server-side; clients send only `check_in_at`/`check_out_at`/`status`.
- Standard workday = 480 min (overtime threshold) — a single constant, easily tuned.
- Writes admin-only (managers read team; per spec). Employee self-check-in/out flows are not in this scope (admin records attendance in v1).

## 8. Out of scope (untouched)
Frontend (F6), Reports, Analytics, Dashboard, leave/holiday automation, biometric ingestion.

**V4 Attendance backend complete. Recommended next: F6 Attendance UI (calendar/history), then V5 Reports.**
