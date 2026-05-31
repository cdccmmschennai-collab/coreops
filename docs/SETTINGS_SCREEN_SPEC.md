# Settings Screen Spec

> Route `/settings` · all roles (Profile, Preferences); **admin** (Users & Roles). No-code UX spec. This is the only v1 screen whose admin tab is **already backed** (`/users` endpoints from `openapi-v1.yaml`); Profile reads `/auth/me`. Flags a real API gap (self password change).

## Purpose
Personal account settings for everyone (profile, security, preferences) and, for admins, **Users & Roles** management (the live `/users` API: create users, set role, reset password, activate/deactivate).

## Layout
PageHeader (title) → left vertical tab rail (or top tabs): **Profile · Security · Preferences · Users & Roles (admin) · SSO (admin, deferred)** → right content panel per tab.

## Desktop wireframe — Profile
```
┌────────────┬─────────────────────────────────────────────────────────────────────┐
│ ▸ Settings │ Manage / Settings                         ⌘K Search   🔔  ?   (PR) ▾ │
│            ├─────────────────────────────────────────────────────────────────────┤
│            │  Settings                                                             │
│            │  ┌───────────────┐ ┌───────────────────────────────────────────────┐ │
│            │  │ Profile      ◄│ │ Profile                                       │ │
│            │  │ Security      │ │ (PR)  Priya Ramanujan                         │ │
│            │  │ Preferences   │ │ Email     priya@cdccmms.com (read-only)       │ │
│            │  │ Users & Roles │ │ Role      admin            (badge)            │ │
│            │  │   (admin)     │ │ Employee  EMP-00184 · Platform (if linked)    │ │
│            │  │ SSO (admin)   │ │ Last login  May 31, 09:16                     │ │
│            │  └───────────────┘ └───────────────────────────────────────────────┘ │
└────────────┴─────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — Users & Roles (admin)
```
┌───────────────────────────────────────────────────────────────────────┐
│ Users & Roles · 47                         🔍 Search email  [+ Invite] │
│ ┌────┬─────────────────────┬─────────┬─────────┬───────────┬─────────┐ │
│ │    │ Email               │ Role    │ Active  │ Last login│         │ │
│ ├────┼─────────────────────┼─────────┼─────────┼───────────┼─────────┤ │
│ │(PR)│ priya@cdccmms.com   │ admin ▾ │  ●on    │ 09:16     │  ⋯      │ │
│ │(JK)│ jordan@cdccmms.com  │ employee▾│ ●on    │ May 30    │  ⋯      │ │
│ │(RS)│ riya@cdccmms.com    │ employee▾│ ○off   │ —         │  ⋯      │ │
│ └────┴─────────────────────┴─────────┴─────────┴───────────┴─────────┘ │
│ Showing 1–20 of 47                        [ ‹ Prev ] [ Next › ]        │
│  ⋯ menu: Reset password · Deactivate / Activate · Change role         │
└───────────────────────────────────────────────────────────────────────┘
```

## Desktop wireframe — Security
```
┌───────────────────────────────────────────────────────────────────────┐
│ Security                                                                │
│ Change password                                                         │
│  Current password [ •••••••• ]   (see note FD-3)                        │
│  New password     [ •••••••• ]   Confirm [ •••••••• ]                   │
│                                              [ Update password ]        │
│ Active session: this device · signed in 09:16        [ Sign out ]       │
└───────────────────────────────────────────────────────────────────────┘
```

## Mobile wireframe
```
┌─────────────────────────────┐
│ ☰  Settings        🔔 (PR)▾ │
│ [Profile▾]  (tab select)    │
│ ── Profile ──               │
│ (PR) Priya Ramanujan        │
│ Email priya@cdccmms.com     │
│ Role  admin                 │
│ Last login May 31 09:16     │
│ ── Users & Roles (admin) ── │
│ 🔍 Search        [+ Invite] │
│ • priya@…   admin   ●on  ⋯  │
│ • jordan@…  employee●on  ⋯  │
└─────────────────────────────┘
```

## Components
PageHeader, vertical Tabs (rail) / Select on mobile, Card, Field/Input/Select, Badge (role/active), Avatar, DataTable (users), Pagination, SearchInput, Modal (Invite/Create user, Reset password, Confirm deactivate), Button, Toast, EmptyState/ErrorState/Skeleton.

## Tables
**Users & Roles** (admin): Avatar · Email · Role (inline select → `PATCH /users/{id}/role`) · Active (toggle → `PATCH /users/{id}`) · Last login · `⋯` (Reset password, Activate/Deactivate). Guard: last-admin and self-deactivate blocked (server 409 → toast).

## Filters
Users tab: role filter + active/inactive filter (optional); URL `?role=&active=`. Other tabs: none.

## Search
Users tab: email search (`?q=`, server `ILIKE`). Debounced.

## Pagination
Users tab: offset 20/page + "Showing X–Y of N". Other tabs: none.

## Empty states
- Users search no match → "No users match" + Clear.
- Preferences/SSO (deferred) → SSO tab shows "SSO is not configured (coming later)".

## Loading states
Profile → field skeletons; Users table → skeleton rows; inline role/active controls show spinner while patching.

## Error states
- Create user 409 (dup email) → field error; 422 (weak password) → field error.
- Change role / deactivate **last admin** → 409 → toast "Cannot remove the last active admin."
- Self-deactivate → 409 → toast "You cannot deactivate yourself."
- Reset password 403 → toast.
- Profile/users fetch fail → ErrorState + Retry.

## Mobile responsiveness
Tab rail → top dropdown/segmented; user table → stacked cards (email, role badge, active toggle, `⋯`); modals full-screen sheets.

## RBAC behavior
- **all roles:** Profile (read own `/auth/me`), Preferences (client-side: theme/density/timezone display), Security (change own password — see FD-3).
- **admin only:** **Users & Roles** tab (live `/users` API) and **SSO** tab (placeholder, deferred). Non-admins never see these tabs (nav-hidden + route-guarded + API-enforced).
- Invite/Create, role change, password reset, activate/deactivate render only when `can('admin','user.manage')`.

## ⚠️ API gap (FD-3) — must decide before building Security tab
`openapi-v1.yaml` has **no self password-change endpoint** — only admin `PATCH /users/{id}/password`. Options:
1. **Add `PATCH /auth/me/password`** (current + new password) — recommended for real self-service.
2. **v1 = admin-reset only:** hide the Security "change password" form for non-admins; password changes happen via an admin. 
Pick (1) to ship a complete Security tab; otherwise the Security tab is admin-reset-only in v1.

_API: `GET /auth/me` (profile); admin: `GET/POST /users`, `PATCH /users/{id}`, `/role`, `/password`. Self password: **TBD (FD-3)**._
