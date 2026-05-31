# Attendance Screen Spec

> Route `/attendance` · self check-in/out for all; manager/admin team view; viewer read. No-code UX spec. Attendance API is a next backend phase. v1 = web/manual check-in/out + monthly calendar/history (no biometric, no corrections workflow, no leave).

## Purpose
Capture and review daily presence: punch in/out, see the month at a glance, and (manager/admin) view the team's attendance.

## Layout
PageHeader (title + [Check in/out] primary) → KPI row (present / wfh / avg hours) → Tabs: **Calendar** (default) · **History** · (manager/admin) **Team**. Calendar tab = month grid + sidecar (today's punch, legend, shift). History = table. Team = per-member day status grid.

## Desktop wireframe — Calendar tab (self)
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▸ Attend.  │ Workspace / Attendance                    ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│            │  Attendance                                       [ Check out ]       │
│            │  ┌──────────┐┌──────────┐┌──────────┐┌──────────┐                     │
│            │  │Present 18││WFH    3d ││Leave  1d ││Avg 7h36m │                     │
│            │  └──────────┘└──────────┘└──────────┘└──────────┘                     │
│            │  [ Calendar ][ History ][ Team(mgr) ]                                  │
│            │  ┌─────────────────────────────────────────┐ ┌────────────────────┐  │
│            │  │  ‹  May 2026  ›                [Today]   │ │ Today's punch      │  │
│            │  │ Mon Tue Wed Thu Fri Sat Sun              │ │ IN  09:12  OUT  —  │  │
│            │  │  …   …   …   1●  2▫  3▫                   │ │ [ Check out ]      │  │
│            │  │  4●  5●  6◍  7●  8◆  9▫ 10▫               │ │--------------------│  │
│            │  │ 11● 12● 13● 14✦ 15◆ 16▫ 17▫              │ │ Shift  General     │  │
│            │  │ 18● 19◍ 20● 21● 22● 23▫ 24▫              │ │ 09:00–18:00        │  │
│            │  │ 25●25*today 26● 27● 28● 29● 30▫ 31▫       │ │--------------------│  │
│            │  │ ● present ◍ wfh ◆ leave ✦ holiday ▫ wknd │ │ Legend             │  │
│            │  └─────────────────────────────────────────┘ └────────────────────┘  │
└────────────┴─────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — History tab
```
┌─────────────────────────────────────────────────────────────────┐
│ Date    Status     IN      OUT     Hours      [Month: May ▾][⤓]   │
│ May 23  ●present   09:08   18:14   9h 06m                         │
│ May 22  ●present   08:55   18:32   9h 37m                         │
│ May 19  ◍wfh       —       —       8h 00m                         │
│ May 15  ✦holiday   —       —       —                              │
│ Showing 1–22 of 22                                                │
└─────────────────────────────────────────────────────────────────┘
```

## Mobile wireframe
```
┌─────────────────────────────┐
│ ☰  Attendance      🔔 (PR)▾ │
│ [ Check out ]               │
│ ┌──────────┐┌──────────┐    │
│ │Present 18││Avg 7h36m │    │
│ └──────────┘└──────────┘    │
│ [Calendar][History][Team]   │
│ Today  IN 09:12  OUT —      │
│  ‹ May 2026 ›       [Today] │
│ M T W T F S S               │
│ grid of status dots…        │
│ ● present ◍ wfh ◆ leave     │
└─────────────────────────────┘
```

## Components
PageHeader, Button (Check in/out — state-aware), Kpi, Tabs, **Calendar** (month grid w/ status cells + legend), sidecar Cards (today's punch, shift, legend), DataTable (history), Select (month), Segmented, EmptyState/ErrorState/Skeleton. Status color map from `FRONTEND_DESIGN_SYSTEM.md` §6.

## Tables
**History:** Date(+weekday) · Status badge · IN · OUT · Hours (tabular) · `⋯`. Read-only in v1 (no corrections). **Team (manager/admin):** rows = members, columns = days of month, cells = status dot; click cell → that member/day detail (read).

## Filters
History/Team: month selector (`?month=2026-05`), status filter (optional). Team: department/team filter (manager scope auto-applied).

## Search
Team tab: member search (`?q=`). Calendar/History (self): none.

## Pagination
History: month-bounded (≈22 rows) → typically one page; wired for offset if range widens. Team: member pagination (20/page) when org-wide (admin).

## Empty states
- No punches this month → calendar shows neutral cells; History EmptyState "No attendance recorded this month."
- Not checked in today → sidecar shows `IN —` with prominent [Check in].
- Manager team empty → "No team members to show."

## Loading states
KPIs skeleton; calendar grid skeleton (gray cells); history skeleton rows; punch card skeleton. [Check in/out] shows inline spinner while posting.

## Error states
- Check-in/out fails → toast "Couldn't record your punch — try again"; button re-enabled; no optimistic flip on failure.
- Double check-in (409) → toast "You're already checked in."
- Month fetch fail → calendar ErrorState + Retry.

## Mobile responsiveness
Calendar sidecar (punch/shift/legend) moves **above** the grid as compact cards; month grid scrolls; cells show dot + number (label on tap). Team grid → horizontal scroll with sticky member column. KPIs 4→2.

## RBAC behavior
- **employee:** own calendar/history; check in/out (self only); no Team tab.
- **manager:** own + **Team tab** (direct reports) read; no editing others.
- **admin:** Team tab spans org; export (`⤓`); read all; (corrections approval deferred to a later phase).
- **viewer:** read-only self/team views; **no Check in/out** button.
Check-in/out and Team tab visibility gated by `can(role,…)`; punch endpoints are self-scoped server-side.

_API (expected): `POST /attendance/check-in`, `POST /attendance/check-out`, `GET /attendance/me?month`, `GET /attendance?employee_id&month` (team/all)._
