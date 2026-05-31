# Dashboard Screen Spec

> Route `/dashboard` · all roles · scope **self / team / org** by role. No-code UX spec. See `FRONTEND_DESIGN_SYSTEM.md` for components, `api/openapi-v1.yaml` `GET /dashboard/summary`.

## Purpose
The role-aware home: "what's due, what I owe, how are we doing." Employee sees self; manager sees team; admin sees org.

## Layout
PageHeader (greeting + date + primary actions) → KPI row (4 tiles) → two-column band (recent activity / my projects) → charts band (hours this week / team activity). Single scroll, no tabs.

## Desktop wireframe
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▚ CoreOps  │ Workspace / Home                          ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│ WORKSPACE  │  Good afternoon, Priya                       [ This week ] [+ New report]│
│ ▸ Home  ◄  │  Sunday, May 31 · 1 report due today                                  │
│ ▸ Employees│                                                                       │
│ ▸ Projects │  ┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐    │
│ ▸ Attend.  │  │Hours this wk ││Reports 4 / 5 ││In review  2  ││Blockers   1  │    │
│ ▸ Reports  │  │ 32h 15m  ▲+2h││ on track  ▲  ││              ││ needs attn ▼ │    │
│ MANAGE     │  └──────────────┘└──────────────┘└──────────────┘└──────────────┘    │
│ ▸ Settings │  ┌───────────────────────────────┐┌──────────────────────────────┐   │
│            │  │ Recent reports      View all → ││ My projects                  │   │
│            │  │ Date   Project   Hours  Status ││ ● WorkTrack Web · s14    18h │   │
│            │  │ May 23 …Web      7h45m  ●submtd ││ ● Mobile · API            9h │   │
│            │  │ May 22 …Web      8h10m  ●review ││ ● Onboarding              3h │   │
│            │  │ May 21 Mobile    6h05m  ●apprvd ││ ● Q3 planning             2h │   │
│            │  └───────────────────────────────┘└──────────────────────────────┘   │
│            │  ┌───────────────────────────────┐┌──────────────────────────────┐   │
│ (PR) Priya │  │ Hours this week   May 25–31   ││ Team activity (mgr/admin)    │   │
│  Admin   ⎋ │  │ ▁▃▅▂▆▁▁  bar chart            ││ ○ Jordan submitted … 4:32p   │   │
└────────────┴──┴───────────────────────────────┴┴──────────────────────────────┴───┘
```

## Mobile wireframe (<860px)
```
┌─────────────────────────────┐
│ ☰  Home            🔔 (PR)▾ │
├─────────────────────────────┤
│ Good afternoon, Priya       │
│ Sun May 31 · 1 due today    │
│ [ + New report ]            │
│ ┌───────────┐┌───────────┐  │
│ │Hours 32h15││Reports 4/5│  │
│ └───────────┘└───────────┘  │
│ ┌───────────┐┌───────────┐  │
│ │In review 2││Blockers  1│  │
│ └───────────┘└───────────┘  │
│ Recent reports     View all │
│ • May 23 …Web 7h45m ●submtd │
│ • May 22 …Web 8h10m ●review │
│ My projects                 │
│ • WorkTrack Web        18h  │
│ Hours this week  [chart]    │
└─────────────────────────────┘
```

## Components
PageHeader, Kpi ×4, Card/CardHeader, DataTable (recent reports), project list (color-dot rows), bar chart (hours/week), activity timeline (manager/admin only), Buttons (This week, New report).

## Tables
**Recent reports** (read-only, last 5): Date · Project · Hours (tabular) · Status badge. Row click → `/reports/[id]`. No inline pagination (links to `/reports`).

## Filters / Search
None on dashboard (it's a summary). `This week` toggle switches the KPI/chart period (this week / last week). ⌘K search lives in TopNav (global).

## Pagination
None — fixed top-N lists with "View all →" linking to the full screen.

## Empty states
- New employee, no data: KPIs show `0` / `—`; Recent reports → EmptyState "No reports yet — submit your first daily report" + [New report].
- Manager with no team activity → timeline EmptyState "No team activity today."

## Loading states
KPI tiles → 4 skeleton tiles; tables → 5 skeleton rows; charts → skeleton block. Greeting renders immediately from cached `/auth/me`.

## Error states
- `/dashboard/summary` fails → section ErrorState with Retry (KPIs + lists); greeting still shows.
- `401` → redirect to login.

## Mobile responsiveness
KPI grid 4→2 columns; two-column bands stack; charts fluid; timeline collapses under recent reports. Header actions wrap; "This week" becomes a compact segmented control.

## RBAC behavior
- **employee:** self scope — own hours/reports/blockers; no team activity card.
- **manager:** team scope — KPIs aggregate direct reports; **Team activity** + "reports pending your review" KPI shown; review CTA.
- **admin:** org scope — org-wide KPIs; team activity across org.
- **viewer:** read-only org/team KPIs; no "New report" action.
Scope is decided server-side (`summary.scope`); client renders cards conditionally via `can(role, …)`.

_API: `GET /dashboard/summary` → `{scope, hours_this_week, reports_submitted, reports_pending_review, present_today, open_blockers}`; recent reports via `GET /reports?limit=5`._
