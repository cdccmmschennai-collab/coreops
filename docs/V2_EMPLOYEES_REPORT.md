# V2 Employees — Backend Report

**Date:** 2026-05-31 · **Branch:** `feature/v1-authentication` · **Status:** complete, tested (43/43), live-smoke verified. **Projects & Attendance NOT started.**

Implements the Employees backend module per the roadmap (built before Projects, since everything depends on Employees). Follows the existing architecture: FastAPI modular monolith, SQLAlchemy ORM, service layer, Alembic, uniform error envelope, JWT/RBAC.

---

## 1. Files created / modified

**Created**
- `backend/app/modules/employees/__init__.py`
- `backend/app/modules/employees/models.py` — `Employee` ORM + `EmployeeStatus` enum
- `backend/app/modules/employees/schemas.py` — `EmployeeOut/Create/Update/Page`
- `backend/app/modules/employees/service.py` — RBAC-scoped reads + admin writes
- `backend/app/modules/employees/router.py` — endpoints
- `backend/alembic/versions/0002_employees.py` — migration
- `backend/tests/test_employees.py` — 18 tests

**Modified**
- `backend/alembic/env.py` — import employees model for autogenerate
- `backend/app/main.py` — register employees router
- `backend/tests/conftest.py` — truncate `employees`; add `login` + `make_employee` fixtures

---

## 2. Data model & migration

**Migration `0002_employees`** (down-revision `0001_users`; verified reversible: up → down → up):
- `CREATE TYPE employee_status AS ENUM ('active','on_leave','exited')`
- `employees` table:

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | `gen_random_uuid()` |
| user_id | uuid → `users.id` ON DELETE SET NULL | **User Account Link** (nullable) |
| employee_code | text | **Employee Number**; partial-unique (alive) |
| first_name, last_name | text | **Full Name** (`full_name` derived) |
| work_email | citext | partial-unique (alive, non-null) |
| phone | text | |
| department | text | **Department** |
| designation | text | **Designation** |
| manager_id | uuid → `employees.id` ON DELETE RESTRICT | self-FK; **no-self-manager** CHECK |
| date_of_joining | date | **Join Date** |
| status | employee_status | **Status** (active/on_leave/exited); default active |
| created_by/updated_by | uuid | audit actor |
| created_at/updated_at/deleted_at | timestamptz | timestamps + soft-delete |

Indexes: partial-unique `employee_code`, `work_email`, `user_id` (all `WHERE deleted_at IS NULL`); `manager_id`, `status` (alive).

---

## 3. Endpoints (`/api/v1/employees`)

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/employees` | any auth (scoped) | list + `q` search, `status`/`department`/`manager_id` filters, `limit`/`offset` pagination |
| POST | `/employees` | **admin** | create (unique code/email/user-link, manager validation) → 201 |
| GET | `/employees/{id}` | any auth (scoped) | read one |
| PATCH | `/employees/{id}` | **admin** | update (no-self-manager, email-uniqueness) |
| DELETE | `/employees/{id}` | **admin** | deactivate = soft-delete + status `exited` → 204 |
| GET | `/employees/{id}/team` | **admin / own manager** | direct reports (`manager_id = {id}`) |

**RBAC (as specified):**
- **admin** — full access.
- **manager** — read access, **scoped to their team** (`manager_id = own employee id`); may read self.
- **employee** — read access, **own record only**.
- **viewer** — read access, **all**.

**Search:** `q` ILIKE over first/last name, employee_code, work_email. **Filters:** status, department (ILIKE), manager_id. **Pagination:** `{items,total,limit,offset}`, limit 1–100 (default 20).

**Error mapping:** 401 unauth · 403 forbidden (scope) · 404 not found · 409 duplicate code/email/user-link · 422 invalid manager / self-manager / validation.

---

## 4. Tests — 18 new, **43 total passing**

`docker compose run --rm --no-deps --entrypoint pytest backend -q` → `43 passed`.

- **CRUD:** create+get, duplicate code 409, missing fields 422, invalid manager 422, update, self-manager 422, deactivate removes from list + 404 after, unknown 404.
- **List:** pagination (total vs page), search by name, filter by status.
- **RBAC:** viewer read-but-not-create (403); employee sees only self; employee can't view other (403); manager sees team only; manager non-team get 403; manager can't create (403); `/team` returns reports.

Test infra: `wms_test` DB (migrations applied), per-test truncate (`employees, users CASCADE`) + Redis flush; fixtures `make_user`, `make_employee`, `login`, `auth_header`.

---

## 5. Verification steps

**Automated:** `py_compile` clean; migration up/down/up reversible; full pytest 43/43.

**Live (running stack, port 8100):**
```bash
# admin token
TOKEN=$(curl -s -X POST localhost:8100/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ops@cdccmms.com","password":"<pw>"}' | jq -r .access_token)
# create + list
curl -s -X POST localhost:8100/api/v1/employees -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"employee_code":"EMP-LIVE-9","first_name":"Ada","last_name":"Lovelace"}'   # -> 201
curl -s "localhost:8100/api/v1/employees?q=ada" -H "Authorization: Bearer $TOKEN" # -> {items:[Ada], total:1}
curl -s -o /dev/null -w '%{http_code}' localhost:8100/api/v1/employees             # -> 401 (unauth)
```
Observed: create **201**, list returns `Ada Lovelace` (`full_name`, status `active`), unauth **401**. OpenAPI (`/api/v1/openapi.json`) lists `/employees`, `/employees/{employee_id}`, `/employees/{employee_id}/team`. Interactive docs: `/api/v1/docs`.

---

## 6. Notes / decisions
- **Manager scope:** "Manager: read access" is implemented as **team-scoped** read (consistent with the broader RBAC matrix), not read-all. Documented here in case read-all is preferred.
- **Employee self-edit** deferred — employees have **read** of their own record; profile self-edit (matrix) is a later enhancement (writes are admin-only in V2).
- **Deactivate = soft-delete** (`deleted_at` + status `exited`); the record leaves active lists but is retained. A separate hard-delete/retention job is out of scope.
- `full_name` is a derived field on `EmployeeOut` (no stored/generated column in v1).
- Structure now, real data later — table + endpoints exist; load real employees via `POST /employees` or a future import.

## 7. Remaining (next phases — not started)
- **F4 Frontend Employees** (table/search/filters/pagination/detail/create/edit/deactivate) — can build against this live API.
- **V3 Projects** backend (build after Employees).
- Employee self password-change / self-profile-edit (FD-3 + matrix) if desired.

**V2 Employees complete. Awaiting direction (recommended next: F4 Frontend Employees against this API, or V3 Projects backend).**
