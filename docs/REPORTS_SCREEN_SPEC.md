# Reports Screen Spec

> Routes `/reports` (list), `/reports/new` (create), `/reports/[id]` (detail/review) · self submit/edit for all; manager/admin review (team/all); viewer read. No-code UX spec. Daily-reports API is a next backend phase. v1 = single-entry daily report (one primary project + hours + task counts + remarks), lifecycle draft→submitted→approved/rejected.

## Purpose
The core loop: employees file a daily report; managers review/approve. List is filterable/exportable; detail supports submit/edit (owner) and approve/reject (reviewer).

## Layout
**List:** PageHeader (title + [Export CSV] + [New report]) → Tabs (All / Submitted / In review / Drafts) → Toolbar (search + filter chips) → DataTable (paginated). **New/Edit:** form (day details → work: project + counts → remarks) with sidecar totals; Save draft / Submit. **Detail:** header (status) → report body → review panel (manager/admin: Approve/Reject + note).

## Desktop wireframe — list
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▸ Reports  │ Workspace / Reports                       ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│            │  My reports                              [ ⤓ Export CSV ] [+ New]     │
│            │  [ All 48 ][ Submitted 6 ][ In review 2 ][ Drafts 1 ]                 │
│            │  🔍 Search…  [Project: …Web ×][From May 1][To May 31]      Clear all  │
│            │  ┌──┬───────────────┬─────────┬──────────┬───────┬─────────┬────────┐ │
│            │  │☐ │ Report        │ Project │ Submitted│ Hours │ Reviewer│ Status │ │
│            │  ├──┼───────────────┼─────────┼──────────┼───────┼─────────┼────────┤ │
│            │  │☐ │ May 24 — daily│ …Web    │ 4:32 PM  │ 4h45m │ (MV)Marco│●review│ │
│            │  │☑ │ May 23 — daily│ …Web    │ 5:18 PM  │ 7h45m │ (MV)Marco│●submtd│ │
│            │  │☐ │ May 22 — daily│ …Web    │ 4:50 PM  │ 8h10m │ (MV)Marco│●apprvd│ │
│            │  │☐ │ May 18 — draft│ …Web    │ —        │ 1h20m │ —       │●draft │ │
│            │  ├──┴───────────────┴─────────┴──────────┴───────┴─────────┴────────┤ │
│            │  │ Showing 1–8 of 48                  [ ‹ Prev ] [ Next › ]         │ │
│            │  └────────────────────────────────────────────────────────────────┘ │
└────────────┴─────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — new/edit
```
New daily report                      [ Discard ] [ Save draft ] [ Submit report ]
Sunday, May 31, 2026 · auto-saved 12s ago
┌───────────────────────────────────────────────┐ ┌──────────────────────┐
│ Day details                                    │ │ Today's totals       │
│ Day status [Working ▾] Location [Office ▾]     │ │ Hours      4h 45m    │
│ Shift [General 09–18 ▾]                        │ │ Tasks done       6   │
├────────────────────────────────────────────────┤ │ Tasks open       3   │
│ Work                                           │ │----------------------│
│ Project [WorkTrack Web · s14 ▾]                │ │ Locks at midnight.   │
│ Hours [ 4.75 ]  Tasks done [6]  Tasks open [3] │ │ Editable until then. │
├────────────────────────────────────────────────┤ └──────────────────────┘
│ Remarks  [ textarea … ]                        │
└───────────────────────────────────────────────┘
```

## Desktop wireframe — detail / review
```
← Reports
┌───────────────────────────────────────────────────────────────────────┐
│ May 24 — daily   ●in review        (owner: Priya R.)                    │
│ Project WorkTrack Web · s14 · 4h 45m · tasks 6 done / 3 open            │
│ Remarks: Reviewed token migration … Blocked on design tokens.          │
├───────────────────────── Review (manager/admin) ───────────────────────┤
│ Note [ optional … ]                          [ Reject ]   [ Approve ✓ ] │
└───────────────────────────────────────────────────────────────────────┘
```

## Mobile wireframe — list
```
┌─────────────────────────────┐
│ ☰  Reports         🔔 (PR)▾ │
│ [+ New]            [⤓ CSV]  │
│ [All][Submtd][Review][Draft]│
│ 🔍 Search…        [Filter ▾]│
│ ┌─────────────────────────┐ │
│ │May 24 — daily   ●review │ │
│ │ …Web · 4h45m · Marco    │ │
│ ├─────────────────────────┤ │
│ │May 23 — daily   ●submtd │ │
│ └─────────────────────────┘ │
│ Showing 1–8 of 48  [Next ›] │
└─────────────────────────────┘
```

## Components
PageHeader, Tabs (status), SearchInput, FilterBar/FilterChip, DataTable, Badge, Avatar (reviewer), Pagination, Button (New, Export, Save draft, Submit, Approve, Reject), Field/Input/Select/Textarea/PillSelect (form), Kpi/sidecar (totals), Modal (confirm reject?), EmptyState/ErrorState/Skeleton, Toast.

## Tables
Columns: ☐ select · Report (date + "N entries · preview") · Project · Submitted (time) · Hours (tabular) · Reviewer (avatar) · Status badge · `⋯`. Row → `/reports/[id]`. Bulk select enables CSV export of selection (admin/manager) — optional v1.

## Filters
Status (via tabs), Project (select), Date range (From/To), Employee (manager/admin only). Chips + URL (`?status=&project=&from=&to=&employee_id=`). "Clear all".

## Search
Debounced free-text over report preview/remarks/project (`?q=`).

## Pagination
Offset, 8–20/page; "Showing X–Y of N" + Prev/Next; preserves tab+filters in URL.

## Empty states
- No reports → "No reports yet — file your first daily report" + [New report].
- Tab/filter no match → "No reports match these filters" + Clear.
- Manager review queue empty → "Nothing to review — you're all caught up."

## Loading states
Tabs render instantly (counts skeleton); table → skeleton rows; form → field skeletons; detail → body skeleton. Submit/Approve show inline button spinners.

## Error states
- List fail → ErrorState + Retry.
- **Edit conflict (409)** — report changed/locked (past `report_date` or already reviewed) → non-destructive banner "This report is locked / changed — reload" (no silent overwrite).
- Submit/review 403 → toast "You can't review this report" (e.g., author≠reviewer, out of scope).
- 422 (hours>24, negative counts) → inline field errors.
- Detail 404 → "Report not found."

## Mobile responsiveness
Table → stacked cards (date+status, project·hours·reviewer line). Form single-column; sidecar totals move to a sticky bottom summary bar with [Submit]. Review actions become a sticky action bar.

## RBAC behavior
- **employee:** sees **own** reports; create/edit/submit own; edit allowed only while draft/submitted & unreviewed & date not past (D-V1-2); cannot review.
- **manager:** own + **team** reports; **Review** (Approve/Reject) on team reports; **author ≠ reviewer** enforced (can't approve own).
- **admin:** all reports; review any; export.
- **viewer:** read-only list/detail; no New/Review/Export.
`[New]` hidden for viewer; review panel renders only when `can(role,'report.review')` and the report is in `submitted/in_review` and not authored by the current user.

_API (expected): `GET /reports?status&project_id&from&to&employee_id&q&limit&offset`, `POST /reports`, `GET/PATCH /reports/{id}`, `POST /reports/{id}/submit`, `POST /reports/{id}/review`, `GET /reports/export?format=csv`._
