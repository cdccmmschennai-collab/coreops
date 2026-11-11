# Plan Submission Tracker - Technical Reference

**Module:** `project_deliverables` (backend) / `features/project-deliverables` (frontend)
**Decision record:** [ADR-003 Amendment 2](./ADR-003-project-progress-and-submission-model.md#amendment-2---deliverable-submission-deadlines-2026-11-11)
**Audit / phase plan:** [audits/project-deliverables-deadline-tracker-phase1-audit.md](./audits/project-deliverables-deadline-tracker-phase1-audit.md)

This page describes the behaviour **as implemented**. When it disagrees with
the audit's plan, the code and this page win.

A *deliverable* is one planned client submission on a project (for example
"MDR VDR", "FMTL"). Its activity name is **free text** - there is no activity
type. Its `target_date` is the **planned submission date**, i.e. the deadline.

---

## 1. Data and API

No migration was added for the tracker. It works on the existing
`project_deliverables` and `deliverable_changes` tables.

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/api/v1/deliverables` | Any signed-in user | Cross-project list, scoped to what the caller may view (Section 4). Used by the PM dashboard card and the Deliverables page. |
| GET | `/api/v1/deliverables/{id}` | Viewers of the project | Detail page. |
| GET | `/api/v1/deliverables/{id}/changes` | Viewers of the project | Timeline (change history). |
| GET | `/api/v1/projects/{project_id}/deliverables` | Viewers of the project | Per-project list. |
| POST | `/api/v1/projects/{project_id}/deliverables` | Managers (Section 4) | Create. |
| PATCH | `/api/v1/projects/{project_id}/deliverables/{id}` | Managers | Update (details, dates, status). |
| DELETE | `/api/v1/projects/{project_id}/deliverables/{id}` | Managers | Hard delete; its `deliverable_changes` rows cascade. |

Every `DeliverableOut` carries three read-only fields on top of the stored columns:

| Field | Type | Source |
|---|---|---|
| `days_remaining` | `int \| null` | Computed on read (Section 2). |
| `deadline_state` | enum (Section 2) | Computed on read (Section 2). |
| `can_manage` | `bool` | Stamped by the service for the **calling** user (Section 4). A display hint only - every write is re-checked server-side. |

`project_code` / `project_name` are filled on the cross-project list and on
the detail endpoint; the per-project list leaves them `null`.

Frontend types are hand-written in `features/project-deliverables/types.ts`.
A type-level guard in that file fails `tsc` if they drift from the generated
`DeliverableOut` in `src/types/openapi.ts`.

---

## 2. Deadline calculation

Source: `backend/app/modules/project_deliverables/deadline.py` (pure, no I/O).

- **"Today" is the business date in Asia/Kolkata** (`business_today()`), never
  the server's local date. The containers run in UTC, which is still the
  previous day before 05:30 IST.
- `days_remaining = target_date - today` in whole calendar days. **Weekends and
  holidays are counted** - there is no working-day calendar here.
- `days_remaining` is `null` when there is no `target_date` or the deliverable
  is completed.

| `deadline_state` | Rule (checked top to bottom) |
|---|---|
| `completed` | `status == completed`, whatever the date |
| `no_deadline` | no `target_date` |
| `overdue` | `days_remaining < 0` |
| `due_today` | `days_remaining == 0` |
| `urgent` | `days_remaining == 1` |
| `due_soon` | `2 <= days_remaining <= 5` (`REMINDER_WINDOW_DAYS = 5`) |
| `on_track` | `days_remaining > 5` |

**The state is never stored.** The stored `status` stays exactly
`planned | completed`. That is a hard rule: the leave-review *Deliverable Impact*
check selects `status == planned`, and a stored "overdue" value would silently
drop rows out of it.

**The frontend never recomputes the state** from the browser clock. It only
displays `deadline_state` and `days_remaining` as received.

---

## 3. Reminder behaviour

Reminders are **on-screen only**: there is no reminder email, bell
notification, login banner or scheduled job for deadlines.

### PM dashboard - Submission Reminders card
`frontend/src/features/dashboard/submission-reminders-card.tsx`, rendered only on
the Project Manager dashboard.

- Data: the same `GET /deliverables` query and React Query cache as the
  Deliverables page, so any deliverable change refreshes both.
- Completed deliverables are excluded.
- One flat list, **no group headings**. Priority is conveyed by order and the
  status badge (`features/project-deliverables/reminders.ts`):
  1. overdue  2. due today  3. due tomorrow (`urgent`)  4. 2-5 days (`due_soon`)
  5. later (`on_track`)  6. no deadline.
  Within a group: earliest `target_date` first, then name.
- At most **6 rows**; the remainder becomes a "+N more pending" link to the
  Deliverables page.
- Each row shows the activity name, project number, planned submission date,
  deadline badge and countdown ("13 days remaining", "Due today",
  "2 days overdue"), and links to `/projects/deliverables/{id}`.
- Empty state: "No pending deliverables."

Badge tones: on track = neutral; 2-5 days = amber; 1 day = stronger amber;
due today = prominent warning; overdue = red.

### Deliverable Detail page
`/projects/deliverables/{id}` shows the same countdown as a pill in the
"Deliverable Details" header ("13 days left", "Due today", "4 days overdue").
Nothing is shown for completed or undated deliverables. The Project Head name
comes from the existing `GET /projects/{id}`; "Not assigned" when there is none.

### Notifications that do exist (unchanged by the tracker)
In-app notifications fan out to every project member, deep-linking to the
detail page. They are best-effort: a failure never rolls back the change.

| Event | Type |
|---|---|
| Deliverable created | `deliverable_planned` |
| `target_date` changed | `deliverable_date_updated` |
| Marked completed | `deliverable_completed` (date = `completion_date`, else IST today) |

---

## 4. Permissions

Resolved through the central `app.core.authz` helpers, never by
`project_members.role`.

| Who | View | Manage (create / edit / change status / delete) |
|---|---|---|
| Project Manager (`role = project_manager`) | Every live project | Every live project |
| Assigned Project Head (`projects.head_employee_id`) | Projects they head | **Only** the projects they head |
| Project member (team_lead, contributor, qc alike) | Projects they belong to | No - a team-lead project role grants nothing extra |
| Anyone else | No (403) | No (403) |

- Deliverables of **soft-deleted projects** are invisible to everyone.
- Heading project A grants nothing on project B.
- `can_manage` on each row reflects exactly this rule for the caller.
- Deliverables page (`all-deliverables-view.tsx`): Edit/Delete show per row
  from `can_manage`. "Add Deliverable" shows for a PM (all projects) or a Head
  (project picker limited to the projects they head; `manage-access.ts`).

---

## 5. Status transitions, reasons and history

Stored statuses: `planned`, `completed`.

| Change | Reason required? | Timeline (`deliverable_changes`) | Audit log |
|---|---|---|---|
| `planned` -> `completed` | **No** | Yes, with the system reason "This activity has been delivered." Shown as "<activity> has been delivered." | Yes |
| `completed` -> `planned` (**reversal**) | **Yes** | Yes, with the user's reason | Yes |
| `target_date` changed (planned submission) | **Yes** | Yes (`due_date`) | Yes |
| `planned_start_date` changed | **Yes** | Yes | Yes |
| Name / description / owner / `completion_date` | No | No | No |

- A missing or blank reason on a tracked change returns **422** and nothing is saved.
- One reason covers every tracked field in the same request.
- History rows are append-only from the API: no endpoint edits or deletes
  them. They go only when the deliverable itself is deleted (FK cascade).
- **After a reversal** the deliverable is `planned` again, so `deadline_state`
  is recomputed from `target_date` straight away. A past date shows as
  `overdue` at once.
- The backend does **not** set or clear `completion_date` on a status change;
  it stores whatever the client sends.

---

## 6. Tests

| Area | File |
|---|---|
| Deadline ladder, IST date, RBAC, scoping, reasons, history, Deliverable Impact regression | `backend/tests/test_project_deliverables.py` |
| Reminder ordering, filtering, cap, labels, links; card source guard | `frontend/src/features/project-deliverables/reminders.test.ts` |
| Detail page: Project Head display, project label/link, countdown; layout source guard | `frontend/src/features/project-deliverables/detail-view.test.ts` |
| Deliverables page management controls (PM / Head / member) | `frontend/src/features/project-deliverables/manage-access.test.ts` |

`node --test` has no React renderer, so UI structure is guarded by asserting on
component source. Behaviour that matters lives in the pure `.ts` modules,
which are tested directly.
