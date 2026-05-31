# CoreOps — Product Blueprint

**Status:** Draft for approval · **Date:** 2026-06-01 · **Owner:** Product
**Purpose:** Define the complete, enterprise-grade product surface for CoreOps WMS so the
remaining modules (Dashboard, Attendance UX, Reports, Analytics, Settings) are built to a single,
coherent vision. **Specification only — no code.**

**Parents:** [PRODUCT_SPEC_V1.md](./PRODUCT_SPEC_V1.md) · [DAILY_WORK_REPORTS_SPEC.md](./DAILY_WORK_REPORTS_SPEC.md)

---

## 0. Context & ground truth

### 0.1 What exists today
- **Live (backend + UI):** Auth/RBAC, Employees, Projects, Attendance. Settings→Users (list only).
- **Placeholder/none:** Dashboard (static card), Reports (none), Analytics (none), Settings tabs (none), DWR (models+migration only).
- **Roles:** `admin`, `manager`, `employee`, `viewer` (fixed enum).
- **Attendance policy (locked):** workday 480 min, OT after 480, half-day 240.

### 0.2 Reusable frontend kit (already built — reuse, don't reinvent)
`Card`, `Table`, `Badge` (semantic variants), `Button`, `Select`, `Input`, `Textarea`, `Form` (RHF),
`DropdownMenu`, `AlertDialog`, `Avatar`, `Skeleton`, `Separator`, `Sonner` (toasts),
`Pagination`, `SearchInput`, `EmptyState`, `ErrorState`, `TableSkeleton`, `FullScreenLoader`,
`PageHeader`, `AppShell`, `Sidebar`, `TopNav`, `RequireCapability`.

### 0.3 New shared primitives this blueprint introduces (build once, reuse everywhere)
- **`KpiCard`** — label, big value, optional delta/trend, optional icon, optional drill-through link.
- **`StatTile` / `MetricRow`** — compact metric groupings.
- **`ChartCard`** — `Card` wrapper around a chart with title + period control + empty/loading states.
- **`Chart primitives`** — line, bar, donut/pie, stacked-bar. **Requires a charting decision (§7).**
- **`CalendarMonth`** — month grid for attendance (color-coded day cells).
- **`FilterBar`** — standardized filter row (date range, dept, project, status, employee).
- **`SegmentedControl` / period toggle** — Today / Week / Month.
- **`Tabs`** — for Settings + multi-view pages (not yet in the kit; shadcn `tabs`).
- **`ExportMenu`** — CSV / XLSX dropdown with progress + toast.

> **§7 charting decision is a prerequisite** for Dashboard charts and all of Analytics.

### 0.4 Cross-cutting backend pattern for read surfaces
Dashboard/Reports/Analytics need **new read-only aggregation endpoints** (no writes). They compute
**live** per request in v1 (single-tenant, small data). Each is **role-scoped** server-side using the
existing `_current_employee` helper and the manager "team = direct reports (`employees.manager_id`)" rule.

---

# 1. Dashboard

Role-specific landing pages at `/dashboard`. One route; the rendered content branches on role.
Default period: **This month**, with a Today/Week/Month `SegmentedControl` where meaningful.

### 1.A Admin Dashboard
- **Business purpose:** org-wide pulse — staffing, attendance health, project load — in one glance.
- **Target user:** `admin` (ops/HR leadership).
- **KPI cards (exact):**
  1. Total Employees (active)
  2. Present Today (count + % of active)
  3. Absent Today (count)
  4. On Leave Today (count)
  5. Active Projects
  6. Attendance % (today, org)
- **Widgets:**
  - **Attendance breakdown today** (donut: present/absent/leave/half-day/holiday/weekend).
  - **Projects by status** (bar: planning/active/on_hold/completed).
  - **Pending work-report reviews** (count + link to `/work-reports?status=submitted`).
  - **Headcount by department** (horizontal bar, top 6).
  - **Recently joined** (list, last 5 by `date_of_joining`).
- **Charts:** Attendance trend (line, last 30 days, org attendance %); Department headcount (bar); Today breakdown (donut).
- **Required backend APIs:**
  - `GET /dashboard/admin/summary` → the 6 KPIs + today breakdown counts.
  - `GET /dashboard/admin/attendance-trend?days=30` → series of {date, present, total, pct}.
  - `GET /dashboard/admin/headcount-by-department` → [{department, count}].
  - `GET /dashboard/admin/projects-by-status` → [{status, count}].
  - (reuse) `GET /work-reports?status=submitted&limit=1` for the pending count.
- **Required frontend components:** `KpiCard` ×6, `ChartCard` (line/donut/bar), `EmptyState`, drill links.
- **Wireframe:**
```
┌ PageHeader: "Good morning, <name>"            [Today|Week|Month] ┐
├ KPI row: [Employees][Present][Absent][On Leave][Projects][Att %] ┤
├ ┌ Attendance trend (line, 30d) ───────┐ ┌ Today breakdown (donut) ┐ ┤
│ └──────────────────────────────────────┘ └─────────────────────────┘ │
├ ┌ Headcount by dept (bar) ─────────────┐ ┌ Projects by status (bar)┐ ┤
│ └──────────────────────────────────────┘ └─────────────────────────┘ │
├ ┌ Pending reviews ┐ ┌ Recently joined (list) ───────────────────────┐ ┤
└ └─────────────────┘ └────────────────────────────────────────────────┘ ┘
```
- **Priority:** **P1** (KPI row + today donut + attendance trend). P2: dept/project bars, recently-joined.

### 1.B Manager Dashboard
- **Business purpose:** run my team day-to-day — who's in, what needs my review.
- **Target user:** `manager` (scoped to direct reports).
- **KPI cards (exact):**
  1. My Team Size
  2. Present Today (team)
  3. Absent Today (team)
  4. On Leave Today (team)
  5. Team Attendance % (today)
  6. Pending Reviews (team work reports `submitted`)
- **Widgets:** Team attendance today (list: member · status badge); Team projects (active projects the team is on); Reports awaiting my approval (list → review).
- **Charts:** Team attendance trend (line, 14–30 days); team status breakdown (donut, today).
- **Required backend APIs:**
  - `GET /dashboard/manager/summary` (team-scoped KPIs).
  - `GET /dashboard/manager/team-attendance?date=today` → [{employee, status}].
  - `GET /dashboard/manager/attendance-trend?days=30` (team).
  - (reuse) `GET /work-reports?status=submitted` (team scope applied server-side).
- **Frontend components:** `KpiCard` ×6, team list (`Table`/list), `ChartCard`, review action links.
- **Wireframe:**
```
┌ PageHeader: "Your team, <name>"               [Today|Week|Month] ┐
├ KPI row: [Team][Present][Absent][Leave][Att %][Pending reviews]  ┤
├ ┌ Team attendance trend (line) ─────┐ ┌ Today breakdown (donut) ┐ ┤
├ ┌ Team attendance today (list) ─────┐ ┌ Awaiting my approval ───┐ ┤
└ └────────────────────────────────────┘ └─────────────────────────┘ ┘
```
- **Priority:** **P1** (KPIs + team today list + pending reviews). P2: trend/donut.

### 1.C Employee Dashboard
- **Business purpose:** my workday at a glance — my attendance, my projects, my reports.
- **Target user:** `employee` (self only). `viewer` sees a read-only org-light variant.
- **KPI cards (exact):**
  1. My Attendance % (this month)
  2. Days Present (this month)
  3. Overtime (this month, hh:mm)
  4. Leave Balance (remaining) *(depends on Leave Policy — §5.E)*
  5. My Active Projects
  6. My Reports This Week (draft/submitted/approved)
- **Widgets:** My recent attendance (last 7 days mini-row, color dots); My projects (cards); My work reports (recent list + "Log today" CTA).
- **Charts:** My attendance this month (mini-calendar or 30-day strip); my hours-by-project (donut, this month — from DWR).
- **Required backend APIs:**
  - `GET /dashboard/me/summary` → personal KPIs.
  - (reuse) `GET /attendance?employee_id=me&from&to`, `GET /projects?member=me`, `GET /work-reports?employee_id=me`.
  - `GET /dashboard/me/hours-by-project?period=month` (from DWR) — P2.
- **Frontend components:** `KpiCard` ×6, mini-calendar strip, project cards, report list + CTA.
- **Wireframe:**
```
┌ PageHeader: "Good morning, <name>"                               ┐
├ KPI row: [Att %][Present][Overtime][Leave bal][Projects][Reports] ┤
├ ┌ My attendance (7-day strip ● ● ○ ●) ┐ ┌ Log today's work [CTA] ┐ ┤
├ ┌ My projects (cards) ────────────────┐ ┌ My recent reports ─────┐ ┤
└ └──────────────────────────────────────┘ └────────────────────────┘ ┘
```
- **Priority:** **P1** (KPIs + projects + reports CTA). P2: hours-by-project, leave balance (needs leave policy).

---

# 2. Attendance (enterprise UX layer)

Attendance CRUD exists. This adds the **enterprise UX**: calendar, summaries, and three role views.
New parent route stays `/attendance`; add a **view switcher** (List | Calendar) and role-scoped tabs.

### 2.A Monthly Attendance Calendar
- **Business purpose:** see a month of attendance at a glance, color-coded; the expected enterprise view.
- **Target user:** all roles (scoped: employee=self, manager=team member picker, admin=any employee).
- **Color coding (uses existing semantic tokens, §0.2 design system):**
  | Status | Color |
  |---|---|
  | Present | green (success) |
  | Absent | red (danger) |
  | Half-day | amber (warning) |
  | Leave | amber/secondary (warning) |
  | Holiday | blue (info) |
  | Weekend | gray (neutral) |
- **Widgets:** month nav (‹ June 2026 ›), employee picker (mgr/admin), legend, day cell shows status dot + hh:mm worked; click a day → day detail/edit (admin/manager).
- **Required backend APIs:**
  - `GET /attendance/calendar?employee_id&month=YYYY-MM` → [{date, status, total_minutes, overtime_minutes}] for the whole month (one call, server fills weekend/holiday gaps).
  - (reuse) existing attendance create/edit for day actions.
- **Frontend components:** **`CalendarMonth`** (new), legend, `Select` (employee), month pager, day popover.
- **Wireframe:**
```
┌ Attendance   [List | ◉Calendar]   Employee:[▼]   ‹ June 2026 ›  ┐
├ Legend: ●Present ●Absent ●Half ●Leave ●Holiday ●Weekend         ┤
├  Mo  Tu  We  Th  Fr  Sa  Su                                     ┤
│  ●1  ●2  ●3  ●4  ●5  ○6  ○7    each cell: dot + "8h 0m"          │
│  ●8  ●9 ...                                                     │
└ Summary cards below (see 2.B)                                   ┘
```
- **Priority:** **P1**.

### 2.B Attendance Summary Cards
- **Business purpose:** quantify the visible period (month) — present/absent/leave/OT totals.
- **Target user:** all (scoped).
- **KPI cards (exact, for selected month + employee/scope):** Present days · Absent days · Half-days · Leave days · Total hours · Overtime hours · Attendance %.
- **Required backend APIs:** `GET /attendance/summary?employee_id&from&to` (or `month`) → counts + minute totals + pct. (Powers both calendar footer and reports.)
- **Frontend components:** `KpiCard` row under the calendar/list.
- **Priority:** **P1** (pairs with calendar).

### 2.C Leave Balances
- **Business purpose:** show remaining leave entitlement; the #1 "is this a real WMS" expectation.
- **Target user:** employee (self), manager (team), admin (org).
- **Dependency:** **requires a Leave Policy + ledger** (§5.E). Leave is currently a *status only* with no
  entitlement model. This is **new domain** (allocation, accrual, consumption).
- **Required backend APIs (new):**
  - `GET /leave/balances?employee_id` → [{leave_type, entitled, taken, remaining}].
  - Backed by `leave_policies` (entitlements) + derivation of "taken" from attendance `leave` days (v1 simple) or a `leave_ledger` (v2).
- **Frontend components:** `KpiCard`/`StatTile` per leave type; small bar (taken vs remaining).
- **Priority:** **P3** (deferred — needs the Leave Policy module; biggest new scope in this blueprint).

### 2.D Employee Self-View
- **Business purpose:** my attendance, my way — calendar + my summary + my OT.
- **Target user:** `employee`.
- **APIs:** `GET /attendance/calendar?employee_id=me`, `GET /attendance/summary?employee_id=me`, `GET /leave/balances?employee_id=me` (P3).
- **Components:** `CalendarMonth` (read-only), summary `KpiCard` row, leave balance (P3).
- **Wireframe:** Calendar (read-only) → summary cards → leave balance strip.
- **Priority:** **P1** (calendar+summary); leave balance **P3**.

### 2.E Manager Team View
- **Business purpose:** monitor team attendance; spot absence patterns; correct records.
- **Target user:** `manager` (direct reports).
- **Widgets:** team day grid (members × days mini-matrix for the month) OR per-member calendar via picker; team summary cards; quick edit (manager can manage team attendance — locked policy §2.2 of product spec).
- **APIs:** `GET /attendance/team-calendar?manager_scope&month` → [{employee, days[]}]; `GET /attendance/summary?team`. Reuse create/edit (team-scoped).
- **Components:** team matrix (extends `CalendarMonth` or a compact grid), member picker, summary cards.
- **Wireframe:**
```
┌ Team attendance   ‹ June 2026 ›                                 ┐
├ Member        1 2 3 4 5 6 7 ... 30   | Att% | OT               ┤
│ A. Kumar      ● ● ● ● ● ○ ○ ...      |  96% | 3h               │
│ B. Singh      ● ● ✕ ● ● ○ ○ ...      |  88% | 0h               │
└─────────────────────────────────────────────────────────────── ┘
```
- **Priority:** **P2** (after self-view calendar; reuses the same calendar engine).

### 2.F Admin Organization View
- **Business purpose:** org-wide attendance oversight + corrections for anyone.
- **Target user:** `admin`.
- **Widgets:** any-employee calendar (picker over all), org summary cards, department filter, link into Reports.
- **APIs:** same calendar/summary endpoints, unscoped; `headcount/attendance` aggregates reused from Dashboard.
- **Components:** `CalendarMonth` + `FilterBar` (department, employee) + summary cards.
- **Priority:** **P2**.

---

# 3. Reports

Canned, parameterized exports. **Formats: CSV + XLSX only.** Synchronous generation in v1.
New route `/reports` with a **catalog → configure → generate/download** flow. Optional lightweight history.

### 3.1 Report catalog (locked v1 set)
| # | Report | Purpose | Params | Scope | Priority |
|---|---|---|---|---|---|
| R1 | **Attendance Summary** | per-employee present/absent/leave/half + total/OT minutes for a period | date range, dept, employee | admin=all, mgr=team | **P1** |
| R2 | **Daily Attendance Register** | one row per employee per day | date range, dept | admin=all, mgr=team | **P1** |
| R3 | **Overtime Report** | OT minutes per employee + totals | date range, dept | admin=all, mgr=team | **P2** |
| R4 | **Employee Directory** | workforce export (code, name, dept, designation, manager, status) | dept, status | admin | **P2** |
| R5 | **Project Assignment Report** | project ↔ member roster (role, dates) | project, status | admin, mgr | **P2** |
| R6 | *(future)* **Work Summary / Hours-by-Project** | DWR hours per employee×project | date range, project | admin, mgr | **P3** |

### 3.2 Report generation flow
- **Business purpose:** self-serve operational/compliance exports without engineering.
- **Target user:** admin (all), manager (team-scoped).
- **Flow:** Catalog grid (cards) → select report → **configure panel** (params via `Form`) → **Generate** → server builds file synchronously → browser download + success toast. Validation: max range 12 months, row cap (e.g. 50k) with a "narrow filters" message.
- **Required backend APIs:**
  - `GET /reports/catalog` → available reports + param schema (or static FE catalog).
  - `POST /reports/{key}/generate` (body = params) → streams `text/csv` or XLSX (`Content-Disposition: attachment`). One endpoint per report key, or one dispatcher with `key`.
- **Required frontend components:** catalog cards, `FilterBar`/`Form` config panel, `ExportMenu` (CSV|XLSX), download handler, `EmptyState` for "no rows".
- **Wireframe:**
```
┌ Reports                                                         ┐
├ ┌Attendance Summary┐ ┌Daily Register┐ ┌Overtime┐ ┌Directory┐  ┤
│ └──────────────────┘ └──────────────┘ └────────┘ └─────────┘   │
├ ── Configure: Attendance Summary ───────────────────────────── ┤
│ Date range [▢▢] Department[▼] Employee[▼]   Format:[CSV|XLSX]   │
│                                              [ Generate ]       │
└─────────────────────────────────────────────────────────────── ┘
```
- **Priority:** flow **P1**; per-report priorities per table.

### 3.3 Export UX
- Format chooser (CSV/XLSX) on the config panel; **Generate** disabled while running; spinner + toast on success/failure; file named `<report>_<range>.<ext>`. No PDF in v1.
- **Priority:** **P1**.

### 3.4 Report history UX
- **Business purpose:** re-download recent exports; light audit of what was run.
- **Target user:** admin/manager.
- **Decision:** v1 reports are **on-demand, not stored** (per product spec). So "history" = an optional
  **client-side recent list** (last N generations: report, params, time — re-run, not re-download).
  True stored history requires a `report_runs` table + file store → **P3** (defer).
- **APIs (only if persisted, P3):** `GET /reports/history`, `GET /reports/history/{id}/download`.
- **Priority:** **P3** (recommend client-side "recent" only in v1, or omit).

---

# 4. Analytics

**Deferred until Dashboard + Reports ship** (per product spec). Specified here for completeness.
Distinct from Dashboard (operational "now") and Reports (row exports): Analytics = **trends over time**.
New route `/analytics` (admin + manager team-scoped). All read-only aggregations.

| View | Business purpose | Target | Backend API | Charts/Components | Priority |
|---|---|---|---|---|---|
| **Attendance trends** | attendance % over weeks/months; spot dips | admin, mgr(team) | `GET /analytics/attendance-trend?bucket=month&from&to&dept` | line + `ChartCard` | **P2** |
| **Leave trends** | leave taken over time / seasonality | admin, mgr | `GET /analytics/leave-trend?bucket=month` *(needs leave data)* | stacked bar | **P3** |
| **Department analytics** | compare depts: headcount, attendance %, OT | admin | `GET /analytics/by-department?metric&period` | grouped bar + table | **P2** |
| **Project analytics** | projects by status, members per project, hours (DWR) | admin, mgr | `GET /analytics/projects?period` (+ DWR hours) | donut + bar | **P3** |
| **Productivity analytics** | logged hours vs attendance, hours-by-project/employee | admin, mgr | `GET /analytics/productivity?period` (DWR + attendance) | bar/heat + table | **P3** |

- **Wireframe (shared):**
```
┌ Analytics   View:[Attendance|Leave|Dept|Project|Productivity]   ┐
├ FilterBar: [period ▼] [bucket: wk/mo ▼] [department ▼]          ┤
├ ┌ Primary chart (ChartCard) ──────────────────────────────────┐ ┤
├ ┌ Secondary chart ┐ ┌ Breakdown table ─────────────────────────┐ ┤
└ └─────────────────┘ └──────────────────────────────────────────┘ ┘
```
- **Overall priority:** **P2–P3**, entirely after Dashboard + Reports.

---

# 5. Settings

Tabbed surface at `/settings` (admin-only for most tabs; Security has a self-service slice).
Uses shadcn **`Tabs`** (new to kit). Existing Users list becomes the first tab.

### 5.A Users & Roles
- **Business purpose:** provision accounts, assign roles, activate/deactivate.
- **Target user:** `admin`.
- **APIs (live):** `GET/POST /users`, `GET /users/{id}`, `PATCH /users/{id}`, `PATCH /users/{id}/role`, `PATCH /users/{id}/password`.
- **Components:** existing users list (built) + detail/create/edit (DWR-paused Settings Phases 4–5) — `Table`, `Form`, `RoleBadge`, `UserStatusBadge`, dialogs.
- **Wireframe:** list (Email·Role·Status·Last login·Actions) → create/edit drawer/page.
- **Priority:** **P1** (resume the paused Phases 4–5).

### 5.B Security
- **Business purpose:** password hygiene — self change + admin reset; visible policy.
- **Target user:** all (self change); admin (reset others).
- **APIs (new):** `PATCH /auth/me/password` (self — the deferred FD-3); reuse `PATCH /users/{id}/password` (admin reset). Surface password policy text.
- **Components:** `Form` (current+new+confirm), policy callout, admin reset action on user detail.
- **Wireframe:**
```
┌ Settings  [Users][◉Security][Organization][Attendance][Leave] ┐
├ Change my password:  Current[…] New[…] Confirm[…]  [Update]   ┤
├ Policy: min 8 chars · login throttle active                   ┤
└─────────────────────────────────────────────────────────────── ┘
```
- **Priority:** **P1** (self change is a basic expectation; needs the new `/auth/me/password`).

### 5.C Organization
- **Business purpose:** org identity/config — display name, timezone, (logo). Backs `PRODUCT_NAME` display.
- **Target user:** `admin`.
- **APIs (new):** `GET /settings/organization`, `PATCH /settings/organization` (key/value config store).
- **Components:** `Form` (name, timezone select, logo upload optional).
- **Priority:** **P2**.

### 5.D Attendance Policy
- **Business purpose:** make the locked policy configurable in one place (workday/OT/half-day minutes).
- **Target user:** `admin`.
- **APIs (new):** `GET /settings/attendance-policy`, `PATCH /settings/attendance-policy` (defaults: 480/480/240). The attendance service reads these instead of hard-coded constants.
- **Components:** `Form` (numeric minutes inputs + helper text).
- **Wireframe:**
```
┌ Attendance Policy                                              ┐
│ Standard workday (min): [480]   Overtime after (min): [480]    │
│ Half-day (min):         [240]                       [ Save ]   │
└─────────────────────────────────────────────────────────────── ┘
```
- **Priority:** **P2** (P1 only if we want config before Dashboard OT metrics; defaults already work).

### 5.E Leave Policy
- **Business purpose:** define leave types + annual entitlements → enables Leave Balances (§2.C).
- **Target user:** `admin`.
- **Scope note:** **largest new domain in this blueprint.** Introduces leave types + entitlements, and a
  way to derive "taken" (v1: count attendance `leave` days; v2: a `leave_ledger`).
- **APIs (new):** `GET/PUT /settings/leave-policy` → [{leave_type, annual_quota}]; feeds `GET /leave/balances`.
- **Components:** `Table`/`Form` editor for leave types + quotas.
- **Wireframe:**
```
┌ Leave Policy                                                   ┐
│ Type            Annual quota                                   │
│ Casual          [12]                                           │
│ Sick            [10]    [+ Add type]                  [ Save ] │
└─────────────────────────────────────────────────────────────── ┘
```
- **Priority:** **P3** (deferred with Leave Balances; sizable — confirm appetite before committing).

---

# 6. Recommended implementation order

Ordered by product value, dependency, and reuse. Each module = backend (model→migration→schemas→service→
router→tests→smoke) then frontend (data→list/view→detail→forms→verify), small commits, phase gates.

| # | Item | Why here | Priority |
|---|---|---|---|
| 1 | **Finish DWR backend** (B3–B6) then **DWR frontend** (F1–F5) | already in flight; unblocks employee dashboard "reports" + future hours analytics | P1 |
| 2 | **Settings: Users CRUD (Phases 4–5)** + **Security (self password, `/auth/me/password`)** | smallest, highest-trust gap; mostly built | P1 |
| 3 | **Attendance Calendar + Summary cards** (self-view) | flagship "feels like a real WMS" UX; reuses attendance API | P1 |
| 4 | **Dashboard: Admin + Manager + Employee** (KPIs + 1–2 charts each) | needs §7 chart decision; consumes attendance + DWR + projects | P1 |
| 5 | **Reports: catalog + generation flow** (R1, R2 first) | high ops value; reuses attendance/employees data | P1 |
| 6 | **Attendance Manager team view + Admin org view** | extends the calendar engine from #3 | P2 |
| 7 | **Settings: Organization + Attendance Policy** | makes policy configurable; low risk | P2 |
| 8 | **Reports: R3–R5** (Overtime, Directory, Project Assignment) | catalog completion | P2 |
| 9 | **Analytics: Attendance trends + Department** | first analytics; after dashboard/reports prove the chart stack | P2 |
| 10 | **Leave Policy + Leave Balances + Leave analytics** | largest new domain; deferred until core is solid | P3 |
| 11 | **Reports history (persisted) + Work-Summary report + Project/Productivity analytics** | depends on DWR maturity + report store | P3 |

---

# 7. Open decisions (blocking where noted)

- **D-BP-1 — Charting library (BLOCKS Dashboard charts + all Analytics).** No chart lib is installed and
  prior rules said "no new libraries." Options: **(A) add `recharts`** (React-standard, ~tree-shakeable) —
  *recommended*; (B) build minimal SVG/CSS charts in-house (no dep, more effort, limited); (C) ship
  Dashboard as **KPI-cards-only** for P1 and defer all charts until a lib is approved. Pick one.
- **D-BP-2 — Tabs primitive:** add shadcn `tabs` for Settings/multi-view (small, recommended yes).
- **D-BP-3 — Leave domain appetite (§2.C/§5.E):** build the Leave Policy + Balances domain in v1 (P3) or
  formally defer to v2? It's the single largest new scope here.
- **D-BP-4 — Reports persistence:** on-demand only (recommended v1) vs stored `report_runs` history (P3).
- **D-BP-5 — Manager scope confirmation:** reaffirm "team = direct reports (`manager_id`)" across
  Dashboard/Attendance/Reports/Analytics (consistent with DWR D-DWR-2).
- **D-BP-6 — Calendar engine:** single `CalendarMonth` reused for self/team/admin (recommended) vs separate components.

---

# 8. Approval

This is a blueprint only — **no code written**. On approval, resume the paused DWR backend (Phase B3),
and thereafter follow §6. Confirm **D-BP-1** (charts) before Dashboard work begins; confirm **D-BP-3**
(leave domain) before committing to §2.C/§5.E.
