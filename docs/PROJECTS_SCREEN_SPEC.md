# Projects Screen Spec

> Routes `/projects` (list) and `/projects/[id]` (detail) · all roles read; admin CRUD. No-code UX spec. Projects API is a next backend phase.

## Purpose
Catalog of projects with status, owner, and burn (allocated vs logged), plus a project hub (contributors, recent reports against the project).

## Layout
**List:** PageHeader (title + count + [New project] for admin) → Toolbar (search + status filter + segmented view: Cards | Table) → grid of project cards (default) or table. **Detail:** back link → header (color dot, name, code, status, owner, dates) → KPI row (hours, reports, on-time, blockers) → burn-down chart → recent reports table + contributors list.

## Desktop wireframe — list (card view)
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▸ Projects │ Workspace / Projects                      ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│            │  Projects · 12        🔍 Search   [Status: active ▾] [▦ Cards|≣ Table]│
│            │                                                  [+ New project](admin)│
│            │  ┌───────────────────────────┐ ┌───────────────────────────┐         │
│            │  │ ● WorkTrack Web · s14  ●active│ ● Mobile · Reporting API ●active│  │
│            │  │ WT-WEB-14                 │ │ MOB-API                   │         │
│            │  │ Members 8   Hours  282h   │ │ Members 5   Hours  144h   │         │
│            │  │ (PR)(MV)(LC)(+5)          │ │ (JK)(AN)(TR)              │         │
│            │  └───────────────────────────┘ └───────────────────────────┘         │
│            │  ┌───────────────────────────┐ ┌───────────────────────────┐         │
│            │  │ ● Onboarding   ●at risk   │ │ ● Q3 planning   ●draft    │         │
│            │  └───────────────────────────┘ └───────────────────────────┘         │
└────────────┴─────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — detail
```
← Projects
┌───────────────────────────────────────────────────────────────────────┐
│ ● WorkTrack Web · sprint 14   ●active     [Members][Settings(admin)][Log]│
│ WT-WEB-14 · led by Marco Velez · 8 contributors · ends May 31           │
│ ┌───────────┐┌───────────┐┌───────────┐┌───────────┐                    │
│ │Hours 282h ││Reports 34 ││Blockers 2 ││On-time 94%│                    │
│ └───────────┘└───────────┘└───────────┘└───────────┘                    │
│ ┌─────────────────────────────────┐ ┌─────────────────────────────┐     │
│ │ Burn down   282h / 320h         │ │ Contributors (8)            │     │
│ │  ╲╲ ideal     ●── actual        │ │ (MV) Marco   Lead     12h   │     │
│ │   ╲ ●╲                          │ │ (PR) Priya   Sr Eng   32h   │     │
│ └─────────────────────────────────┘ └─────────────────────────────┘     │
│ ┌─────────────────────────────────────────────────────────────────┐     │
│ │ Recent reports   Contributor Date Hours Summary Status           │     │
│ └─────────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
```

## Mobile wireframe — list
```
┌─────────────────────────────┐
│ ☰  Projects        🔔 (PR)▾ │
│ 12 · [Status ▾]  [+ New]    │
│ ┌─────────────────────────┐ │
│ │● WorkTrack Web   ●active│ │
│ │ WT-WEB-14               │ │
│ │ 8 members · 282h        │ │
│ ├─────────────────────────┤ │
│ │● Mobile · API    ●active│ │
│ └─────────────────────────┘ │
│ Showing 1–12 of 12          │
└─────────────────────────────┘
```

## Components
PageHeader, SearchInput, Select (status), Segmented (Cards/Table), project Card (color dot, code, status badge, member count, hours, AvatarStack), DataTable (table view + detail recent reports), Kpi, burn-down chart, contributors list, Modal (New project — admin), EmptyState/ErrorState/Skeleton.

## Tables
Table view columns: ● Name · Code · Status · Owner · Members · Hours (tabular) · `⋯` (admin: Edit, Archive). Detail "Recent reports": Contributor · Date · Hours · Summary · Status (row → `/reports/[id]`).

## Filters
Status (active/on_hold/completed/archived), default hides archived. URL `?status=`. (Department filter optional later.)

## Search
Debounced name/code (`?q=`), server `ILIKE`.

## Pagination
20/page offset for table; cards lazy-load or paginate the same way. v1 dataset small (≈12) so single page common; still wired for N.

## Empty states
- No projects → "No projects yet" + [New project] (admin) / passive (others).
- Filter no match → "No projects match" + Clear.
- Detail with no reports → "No reports logged against this project yet."

## Loading states
Cards → 4–6 skeleton cards; table → skeleton rows; detail → KPI + chart + list skeletons.

## Error states
List/detail fetch fail → ErrorState + Retry. Detail 404 → "Project not found." New/Edit 409 (dup code) → field error; 422 (end<start) → field error; 403 → toast.

## Mobile responsiveness
Cards 2-up → 1-up; detail KPIs 4→2; burn-down full-width; contributors below; action buttons collapse into a `⋯` menu.

## RBAC behavior
- **admin:** [New project], [Settings], [Edit], [Archive], manage members.
- **manager:** read all; may be project owner (owner badge); no create/archive in v1 (kept admin-only per matrix) — *flag if managers should create their own projects.*
- **employee / viewer:** read-only; no create/edit; can open detail.
Create/edit/manage controls render only when `can(role,'project.manage')` (admin in v1).

_API (expected): `GET /projects?q&status&limit&offset`, `POST /projects`, `GET/PATCH /projects/{id}`, `GET /projects/{id}/reports`, `GET /projects/{id}/members`._
