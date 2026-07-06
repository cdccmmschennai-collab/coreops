# Phase 1 — Remove the Task Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely remove the standalone Task-assignment module from CoreOps without affecting daily work reports, projects, deliverables, benchmarks, or any live functionality.

**Architecture:** The Task module (`tasks` table, `modules/tasks`, `features/tasks`) is an independent feature. It is *optionally* linked into two surviving modules (`work_report_tasks.task_id`/`task_title`, `activity_requests.task_id`) and has one hidden frontend consumer (Work Reports uses `/tasks/assignable-projects` to detect team-lead status). We cut the hidden dependency first, then remove UI, then backend code, then drop DB objects in a final isolated migration. Every task is one PR that compiles, passes tests, and is independently deployable and rollback-safe.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (Postgres) backend; Next.js + React Query + TypeScript frontend; Docker Compose (`wms-backend-1`, `wms-frontend-1`).

## Global Constraints

- **Git is hands-off for the agent.** Do NOT run `git` (no add/commit/push). Each task ends at a **Checkpoint** where the *user* reviews and commits. "Commit" steps below describe the message the user should use.
- **Backend tests:** `docker exec wms-backend-1 pytest`
- **Frontend typecheck:** `docker exec wms-frontend-1 npm run typecheck` · **Build:** `docker exec wms-frontend-1 npm run build`
- **Every schema/DB change is additive or backward-compatible** until Task 7. No column/table is dropped before the code that uses it is removed and deployed.
- **Deploy order = task order.** A later task assumes the previous task is already deployed.
- **Do NOT touch** `work_report_tasks` (daily-report lines), the `PATCH /work-reports/tasks/{id}/completion` endpoint, `benchmarks` "Overdue Tasks", employee-performance `tasks-tab`, or the separate `project_activities` "Deliverable Activity Tracker" — these are unrelated (naming collision) and stay. **Guardrail:** `test_benchmark_alerts.py` and `test_benchmark_engine.py` hit `/api/v1/work-reports/tasks/{id}/completion` (a WorkReportTask, not the Task module) and must remain green throughout.
- **Test layout is flat:** `backend/tests/test_*.py` with fixtures `client`, `auth_header(email, role=...)`, `make_project`, `make_user`, `make_employee`, `login`. Mirror `backend/tests/test_projects.py` / `test_tasks.py` for new/changed tests.
- **Keep** `audit` `EntityType.TASK` and `TASK_*` action constants (historical `audit_logs` rows reference them).

---

### Task 1: Remove the assigned-task picker from the daily-report form (frontend only)

Removes the optional "link an assigned task" picker. The backend still accepts `task_id` (ignored) after this, so this is backward compatible.

**Files:**
- Modify: `frontend/src/features/work-reports/components/work-report-form.tsx`
- Modify: `frontend/src/features/work-reports/schemas.ts` (task_id at lines ~145-146, 283, 356, 421)

**Interfaces:**
- Consumes: nothing new.
- Produces: report create/edit payloads that no longer contain `task_id` per line.

- [ ] **Step 1: Remove the tasks hook import**
  In `work-report-form.tsx`, delete the import line:
  `import { useTasks } from "@/features/tasks/hooks";`

- [ ] **Step 2: Remove the task-picker data**
  In `work-report-form.tsx`, delete the `myTasksData` / `myTaskById` / `taskOptions` blocks (currently ~lines 289-310) and any JSX that renders the task combobox (search the file for `taskOptions`, `myTaskById`, and the "assigned task" picker field; remove the field and its `form.setValue("...task_id"...)` handlers).

- [ ] **Step 3: Remove `task_id` from the form schema + mappers**
  In `work-reports/schemas.ts`, remove the `task_id` field from the line schema (~145-146), its default (`task_id: ""` ~283), and both mapper sites (~356 `task_id: orNull(t.task_id)` and ~421 `task_id: t.task_id ?? ""`). Ensure the object shapes still typecheck without it.

- [ ] **Step 4: Typecheck + build**
  Run: `docker exec wms-frontend-1 npm run typecheck` — Expected: PASS (no references to `task_id`/`useTasks` remain in work-reports).
  Run: `docker exec wms-frontend-1 npm run build` — Expected: PASS.

- [ ] **Step 5: Manual check**
  Open a new work report and an existing draft: the form loads, activity/sub-activity pickers work, save/submit succeed, and there is no task picker.

- [ ] **Step 6: Checkpoint (user commits)**
  Message: `refactor(work-reports): remove assigned-task picker from report form`

---

### Task 2: Re-source team-lead detection off the tasks endpoint (backend + frontend)

**This is the hidden dependency and must ship before Task 5.** `work-reports-view.tsx` currently calls `/tasks/assignable-projects` (`useAssignableProjects`) to decide `isTeamLead` and build the scoped employee filter. We add an equivalent endpoint in the **projects** module and switch the view to it.

**Files:**
- Modify: `backend/app/modules/projects/schemas.py` (add `LedProjectMember`, `LedProject`)
- Modify: `backend/app/modules/projects/service.py` (add `list_led_projects`)
- Modify: `backend/app/modules/projects/router.py` (add `GET /projects/led`)
- Create: `backend/tests/test_led_projects.py`  (flat layout — mirror `test_projects.py`)
- Create: `frontend/src/features/projects/hooks/use-led-projects.ts` (or add to existing projects hooks)
- Modify: `frontend/src/features/work-reports/components/work-reports-view.tsx`

**Interfaces:**
- Produces (backend): `GET /projects/led` → `list[LedProject]` where
  `LedProject = { project_id: UUID, name: str, code: str, members: list[LedProjectMember] }`,
  `LedProjectMember = { employee_id: UUID, name: str }`.
- Produces (frontend): `useLedProjects()` returning `{ data?: LedProject[] }` with the same shape the view already consumes (`project.members[].employee_id`, `.name`).

- [ ] **Step 1: Write the failing backend test**
  Create `backend/tests/test_led_projects.py` (uses the repo's real fixtures — `auth_header`, `make_project`, `make_user`, `make_employee`, `login`; confirm exact signatures against `test_tasks.py`/`test_projects.py` and adjust the member-seeding calls if a `make_project_member` fixture exists):
```python
from app.modules.users.models import UserRole


def test_led_projects_returns_led_project_with_members(
    client, auth_header, make_project, make_user, make_employee, login
):
    pm = auth_header("pm@example.com", role=UserRole.project_manager)
    project = make_project(code="LED-1")
    lead_user = make_user(email="lead@example.com", role=UserRole.employee)
    lead_emp = make_employee(user=lead_user, first_name="Lead")
    member_emp = make_employee(first_name="Member")
    client.post(f"/api/v1/projects/{project.id}/members", headers=pm,
                json={"employee_id": str(lead_emp.id), "role": "team_lead"})
    client.post(f"/api/v1/projects/{project.id}/members", headers=pm,
                json={"employee_id": str(member_emp.id), "role": "contributor"})

    resp = client.get("/api/v1/projects/led", headers=login(lead_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["project_id"] == str(project.id)
    ids = {m["employee_id"] for m in body[0]["members"]}
    assert str(lead_emp.id) in ids and str(member_emp.id) in ids


def test_led_projects_empty_for_non_lead(
    client, make_user, make_employee, login
):
    user = make_user(email="c@example.com", role=UserRole.employee)
    make_employee(user=user)
    resp = client.get("/api/v1/projects/led", headers=login(user))
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Run it to confirm it fails**
  Run: `docker exec wms-backend-1 pytest backend/tests/test_led_projects.py -v`
  Expected: FAIL (404 / endpoint missing).

- [ ] **Step 3: Add the schemas**
  In `projects/schemas.py`:
```python
class LedProjectMember(BaseModel):
    employee_id: uuid.UUID
    name: str

class LedProject(BaseModel):
    project_id: uuid.UUID
    name: str
    code: str
    members: list[LedProjectMember]
```

- [ ] **Step 4: Add the service function** (ports the exact logic from the retiring `tasks.service.list_assignable_projects`)
  In `projects/service.py`:
```python
def list_led_projects(db: Session, actor: User) -> list["LedProject"]:
    from app.modules.projects.schemas import LedProject, LedProjectMember
    me = _current_employee(db, actor)
    if me is None:
        return []
    led_ids = db.execute(
        select(ProjectMember.project_id).where(
            ProjectMember.employee_id == me.id,
            ProjectMember.role == ProjectMemberRole.team_lead,
        )
    ).scalars().all()
    if not led_ids:
        return []
    projects = db.execute(
        select(Project).where(
            Project.id.in_(led_ids),
            Project.deleted_at.is_(None),
            Project.status != ProjectStatus.archived,
        ).order_by(Project.name)
    ).scalars().all()
    from app.modules.employees.models import Employee, EmployeeStatus
    result: list[LedProject] = []
    for project in projects:
        rows = db.execute(
            select(Employee)
            .join(ProjectMember, ProjectMember.employee_id == Employee.id)
            .where(
                ProjectMember.project_id == project.id,
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
            ).order_by(Employee.first_name, Employee.last_name)
        ).scalars().all()
        result.append(LedProject(
            project_id=project.id, name=project.name, code=project.code,
            members=[LedProjectMember(employee_id=e.id, name=e.full_name) for e in rows],
        ))
    return result
```

- [ ] **Step 5: Add the route**
  In `projects/router.py`:
```python
@router.get("/led", response_model=list[LedProject])
def led_projects(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LedProject]:
    return service.list_led_projects(db, current)
```
  (Import `LedProject` from `projects.schemas`. Place the route BEFORE `/{project_id}` so `/led` isn't captured as a project id.)

- [ ] **Step 6: Run the test to confirm it passes**
  Run: `docker exec wms-backend-1 pytest backend/tests/test_led_projects.py -v` — Expected: PASS.

- [ ] **Step 7: Add the frontend hook**
  Create `frontend/src/features/projects/hooks/use-led-projects.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export interface LedProjectMember { employee_id: string; name: string }
export interface LedProject { project_id: string; name: string; code: string; members: LedProjectMember[] }

export function useLedProjects({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["projects", "led"],
    queryFn: () => api.get<LedProject[]>("/projects/led"),
    enabled,
  });
}
```

- [ ] **Step 8: Switch the view to the new hook**
  In `work-reports-view.tsx`:
  - Replace `import { useAssignableProjects } from "@/features/tasks/hooks";` with `import { useLedProjects } from "@/features/projects/hooks/use-led-projects";`
  - Replace `const { data: assignableProjects } = useAssignableProjects({ enabled: !isManager });` with `const { data: assignableProjects } = useLedProjects({ enabled: !isManager });`
  - No other changes: the consumed shape (`assignableProjects?.length`, `project.members[].employee_id`, `.name`) is identical.

- [ ] **Step 9: Typecheck + build**
  Run: `docker exec wms-frontend-1 npm run typecheck` — Expected: PASS.
  Run: `docker exec wms-frontend-1 npm run build` — Expected: PASS.

- [ ] **Step 10: Manual check**
  As a team-lead employee: Reports page still shows the employee filter and lists reports from led-project members. As a plain contributor: only own reports (empty led list).

- [ ] **Step 11: Checkpoint (user commits)**
  Message: `feat(projects): add GET /projects/led and re-source work-reports team-lead detection off it`

---

### Task 3: Remove the Task UI surface (frontend only)

After Tasks 1–2, nothing outside `features/tasks` imports it.

**Files:**
- Delete: `frontend/src/app/(app)/tasks/` (all: `page.tsx`, `all/page.tsx`, `new/page.tsx`, `[id]/page.tsx`, `[id]/edit/page.tsx`)
- Delete: `frontend/src/features/tasks/` (entire dir)
- Modify: `frontend/src/components/shell/sidebar.tsx` (remove the Tasks nav item, ~line 38; drop the now-unused `ListTodo` import)
- Modify: `frontend/src/features/dashboard/project-manager-dashboard.tsx` (remove the "Assign task" link → `/tasks/new`, ~lines 176-177; drop the now-unused icon import)
- Modify: `frontend/src/lib/rbac.ts` (remove `task.view` and `task.manage` from the `Capability` union and `MATRIX`, ~lines 25-26, 43-44)

- [ ] **Step 1: Verify no external importers remain**
  Run: `grep -rn "features/tasks" frontend/src` — Expected: no matches outside `frontend/src/features/tasks/` itself.

- [ ] **Step 2: Delete the pages and feature directory**
  Delete the two directories listed above.

- [ ] **Step 3: Remove the sidebar item**
  In `sidebar.tsx`, delete the `{ label: "Tasks", href: "/tasks", ... }` entry from `WORKSPACE`, and remove `ListTodo` from the `lucide-react` import.

- [ ] **Step 4: Remove the dashboard link**
  In `project-manager-dashboard.tsx`, delete the `<Link href="/tasks/new">…Assign task…</Link>` block and any icon import it alone used.

- [ ] **Step 5: Remove the capabilities**
  In `rbac.ts`, delete `task.view` and `task.manage` from both the `Capability` type union and the `MATRIX`.

- [ ] **Step 6: Typecheck + build**
  Run: `docker exec wms-frontend-1 npm run typecheck` — Expected: PASS.
  Run: `docker exec wms-frontend-1 npm run build` — Expected: PASS (no dangling imports, no route references `/tasks`).

- [ ] **Step 7: Manual check**
  Sidebar has no Tasks item; PM dashboard has no "Assign task"; navigating to `/tasks` 404s; Reports/Projects unaffected.

- [ ] **Step 8: Checkpoint (user commits)**
  Message: `refactor: remove Task pages, feature, nav, dashboard link, and rbac capabilities`

---

### Task 4: Sever backend seams (columns remain nullable)

Stop reading/writing the Task links from the two surviving modules. DB columns stay (dropped in Task 7).

**Files:**
- Modify: `backend/app/modules/work_reports/service.py` (drop `from app.modules.tasks.models import Task` ~line 38; linked-Task title resolution ~273-279; `task_id=` on `WorkReportTask(...)` ~738-741 and ~830-833)
- Modify: `backend/app/modules/work_reports/schemas.py` (`task_id` on `WorkReportTaskIn` ~26-29 and `WorkReportTaskOut` ~54-59)
- Modify: `backend/app/modules/activity_requests/service.py` (drop `from app.modules.tasks.models import Task` ~20; task lookups/validation/display ~67, 73-79, 201, 273-279, 353, 375, 399)
- Modify: `backend/app/modules/activity_requests/schemas.py` (`task_id` ~20, 36)

**Interfaces:**
- Produces: report lines and activity requests no longer carry `task_id`/`task_title` in their API models or persistence. Existing DB rows keep their (now-unwritten) columns.

- [ ] **Step 1: Remove `task_id` from work-report schemas**
  In `work_reports/schemas.py`, delete `task_id` from `WorkReportTaskIn` and `WorkReportTaskOut`.

- [ ] **Step 2: Remove Task usage in work-reports service**
  In `work_reports/service.py`: delete the `Task` import; delete the linked-Task title-resolution block (~273-279); in both `WorkReportTask(...)` constructions (~738, ~830) remove the `task_id=task.task_id` and any `task_title=` arguments so those columns are simply left NULL.

- [ ] **Step 3: Remove `task_id` from activity-request schemas**
  In `activity_requests/schemas.py`, delete the `task_id` field(s).

- [ ] **Step 4: Remove Task usage in activity-requests service**
  In `activity_requests/service.py`: delete the `Task` import; remove the `task_ids`/`tasks` bulk fetch and `task_title` decoration (~67, 73-79); remove `task_id=` passed into request creation (~201) and into `_create_task_from_request` (`task_id=row.task_id` ~375, `task_title=snap["task_title"]` ~399, and the `task_id` on the constructed line ~353). Where `task_title` was displayed, set it to `None`/omit.

- [ ] **Step 5: Run the backend suite (regression)**
  Run: `docker exec wms-backend-1 pytest -q` — Expected: PASS. Pay attention to `work_reports` and `activity_requests` tests. If any test asserts on `task_id`/`task_title`, update the assertion to reflect its removal (these are the only intended behavior changes).

- [ ] **Step 6: Checkpoint (user commits)**
  Message: `refactor: stop reading/writing Task links in work_reports and activity_requests`

---

### Task 5: Remove the backend Task module

**Precondition:** Tasks 1–4 deployed (no importer of `Task` or `/tasks` remains).

**Files:**
- Delete: `backend/app/modules/tasks/` (`__init__.py`, `models.py`, `router.py`, `schemas.py`, `service.py`)
- Delete: `backend/tests/test_tasks.py` (standalone Task-module test suite)
- Modify: `backend/app/main.py` (remove `from app.modules.tasks.router import router as tasks_router` ~line 37 and `app.include_router(tasks_router, ...)` ~line 96)
- Keep: `backend/app/modules/audit/constants.py` (`EntityType.TASK`, `TASK_*`) unchanged.

- [ ] **Step 1: Confirm no remaining imports**
  Run: `grep -rn "modules.tasks\|import Task\b" backend/app` — Expected: no matches (audit constants use string values, not the `Task` model, so they won't appear).

- [ ] **Step 2: Remove the router mount**
  In `main.py`, delete the tasks import and its `include_router` line.

- [ ] **Step 3: Delete the module directory**
  Delete `backend/app/modules/tasks/`.

- [ ] **Step 4: Delete the Task test suite**
  Delete `backend/tests/test_tasks.py`.

- [ ] **Step 5: Verify the app imports and the suite passes**
  Run: `docker exec wms-backend-1 python -c "import app.main"` — Expected: no ImportError.
  Run: `docker exec wms-backend-1 pytest -q` — Expected: PASS. Confirm `test_benchmark_alerts.py` / `test_benchmark_engine.py` still pass (they use the surviving `/work-reports/tasks/{id}/completion` endpoint).

- [ ] **Step 6: Checkpoint (user commits)**
  Message: `feat: remove backend Task module and its router mount`

---

### Task 6: Regenerate frontend OpenAPI types

**Files:**
- Modify: `frontend/openapi.json` (re-exported from backend)
- Modify: `frontend/src/types/openapi.ts` (regenerated; `/tasks*` paths + Task schemas disappear)

- [ ] **Step 1: Re-export the backend schema**
  Fetch the live schema into `frontend/openapi.json` (backend serves it at `${API_V1_PREFIX}/openapi.json`), e.g.:
  `docker exec wms-backend-1 python -c "import json,app.main; open('/app/../frontend/openapi.json','w').write(json.dumps(app.main.app.openapi()))"`
  — or copy the served `openapi.json` by whatever mechanism the repo already uses. The result must be `frontend/openapi.json` with no `/tasks` paths.

- [ ] **Step 2: Regenerate types**
  Run: `docker exec wms-frontend-1 npm run gen:api`

- [ ] **Step 3: Typecheck + build**
  Run: `docker exec wms-frontend-1 npm run typecheck` — Expected: PASS.
  Run: `docker exec wms-frontend-1 npm run build` — Expected: PASS.

- [ ] **Step 4: Checkpoint (user commits)**
  Message: `chore(frontend): regenerate OpenAPI types after Task module removal`

---

### Task 7: Drop Task DB objects (final, isolated, irreversible)

**Precondition:** Tasks 1–6 deployed and verified in production. **Take a database backup before running.** This is the only irreversible step — keep it as its own PR/deploy.

**Files:**
- Create: `backend/alembic/versions/0053_drop_tasks.py`

- [ ] **Step 1: Write the migration**
  Create `backend/alembic/versions/0053_drop_tasks.py`:
```python
"""0053 drop Task module objects

Drops the work_report_tasks/activity_requests FK columns first, then the tasks
table and its enums. Runs only after all Task code is removed (Phase 1, Tasks 1-6).

Revision ID: 0053_drop_tasks
Revises: 0052_day_status_half_day
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0053_drop_tasks"
down_revision: Union[str, None] = "0052_day_status_half_day"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_report_tasks DROP COLUMN IF EXISTS task_id")
    op.execute("ALTER TABLE work_report_tasks DROP COLUMN IF EXISTS task_title")
    op.execute("ALTER TABLE activity_requests DROP COLUMN IF EXISTS task_id")
    op.execute("DROP TABLE IF EXISTS tasks")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS task_priority")


def downgrade() -> None:
    # Irreversible by policy (data drop). Restore from backup instead.
    raise NotImplementedError("0053_drop_tasks is not reversible; restore from backup.")
```

- [ ] **Step 2: Apply on a prod-shaped copy first**
  Run against a *copy* of production: `docker exec wms-backend-1 alembic upgrade head`
  Expected: success; `\d tasks` gone; `work_report_tasks`/`activity_requests` no longer have `task_id`.

- [ ] **Step 3: Run the suite**
  Run: `docker exec wms-backend-1 pytest -q` — Expected: PASS.

- [ ] **Step 4: Checkpoint (user commits + backs up prod before deploying)**
  Message: `feat(db): drop tasks table and Task FK columns (0053)`

---

## Self-Review

**Spec coverage** (against the Phase-1 inventory from the architecture review):
- Backend APIs/router/service/schemas/models → Tasks 4, 5, 7 ✅
- Notifications (`task_assigned`) → removed with the service in Task 5; historical rows left intact ✅
- Frontend pages/components/nav/dashboard/api-client/rbac → Tasks 1, 3 ✅
- Report task dropdown → Task 1 ✅
- Hidden dependency (`/tasks/assignable-projects` in Work Reports) → Task 2 ✅
- OpenAPI + generated types → Task 6 ✅
- DB tables/columns/enums → Task 7 ✅
- Audit constants intentionally retained → noted in Global Constraints + Task 5 ✅
- Unrelated look-alikes (`work_report_tasks`, benchmarks, tasks-tab, `project_activities` tracker) explicitly excluded → Global Constraints ✅

**Placeholder scan:** none — all commands, file paths, and the migration are concrete. (Task 6 Step 1 offers the repo's existing export mechanism as the alternative, which is expected.)

**Type consistency:** `LedProject`/`LedProjectMember` names and fields are identical across the backend schema (Step 3), service (Step 4), route (Step 5), and frontend hook (Step 7); the frontend consumes only `length`, `members[].employee_id`, `members[].name`, matching the shape the old `AssignableProject` exposed.

**Ordering safety:** Task 2 (re-source) precedes Task 5 (endpoint removal); Task 1 (FE stops sending `task_id`) precedes Task 4 (BE drops the field); Task 4/5 (code) precede Task 7 (DB drop). Each task is independently deployable and rollback-safe except Task 7, which is isolated and backup-guarded.
