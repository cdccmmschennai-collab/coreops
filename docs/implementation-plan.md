# Implementation Plan

> **Gate:** This is a plan only. **No implementation code will be written until this plan is approved** and the blocking decisions below are answered. It operationalizes `roadmap.md` into ordered, reviewable work and follows the structure in `PROJECT_STRUCTURE.md`.

---

## 0. Required process (per the brief)

1. **Extract requirements** — done; captured across `architecture.md`, `frontenddesign.md`, `backenddesign.md`, `databasedesign.md`.
2. **Normalize terminology** — done; brand-agnostic ("the platform"), glossary in `architecture.md` §15.
3. **Resolve naming conflicts** — done; Naming Decision Record (D-001).
4. **Produce documentation** — done; this documentation set is the SSOT.
5. **Produce implementation plan** — this file.
6. **Wait for approval before coding** — see the gate above.

---

## 1. Blocking decisions (must be answered before coding starts)

These gate Phase 1. See `decisions.md` §C.

| Must answer | ID | Blocks |
|---|---|---|
| Backend stack + API style | U-001 | Everything backend |
| Multi-tenancy model | U-010 | Schema shape — **decide before any entity is built** |
| Permission catalog + role grants | U-004 | Authorization |
| Cloud/provider & infra (queue, mail, storage) | U-009 | Deploy + Phase 3 |
| Recover/re-author token file | U-005 | Faithful UI |

Non-blocking but needed soon: U-002 (lock rule, Phase 2), U-007 (count semantics, Phase 2), U-006 (mobile, Phase 3/5).

---

## 2. Workstreams & sequencing

Mapped to roadmap phases. Each item is intended to be a reviewable unit of work.

### Phase 1 — Foundation
1. **Repo scaffold** per `PROJECT_STRUCTURE.md`; CI (lint/test/build), containerized local stack (app + Postgres + queue + storage emulator).
2. **Promote schema** into `database/schema/` with neutralized identifiers (schema names, GUC); set up forward-only migration tool + baseline; seed roles/permissions/leave_types/activity_types/notification_templates.
3. **Platform layer:** config (`PRODUCT_NAME`), HTTP + middleware (auth → RBAC → tx + `current_user_id` GUC → audit context), error envelope, observability, DB/replica access, queue abstraction.
4. **Identity & Access:** login (password + ≥1 SSO), sessions (hashed tokens), password reset, login-attempt rate limiting + lockout, RBAC evaluation (role × scope), audit writes.
5. **Org & People:** employees, departments, locations, shifts, manager hierarchy (`v_employee_org`); Admin → People + Invite.
6. **Frontend foundation:** design-system tokens + primitives + `Brand`/`--product-name`; `AppShell`, Login, Dashboard shell; auth/query/api libs.

**Exit:** sign-in (incl. SSO) → role-appropriate shell; admin invites/manages people; all writes audited; deploy to staging.

### Phase 2 — Core Operations
1. **Projects** (catalog, members, activity types) + Project detail.
2. **Daily Reporting:** report form (day details, work, counts grid, remarks, queries/@mentions), draft auto-save, lifecycle state machine, versioning/history, optimistic concurrency (409), History + CSV export.
3. **Team/review:** review queue, hours-by-member.
4. **Workers:** report-locker; mention extraction; in-app submit/review notifications.
5. **Resolve U-002 (lock rule) and U-007 (count semantics) before finalizing the report model.**

### Phase 3 — Workflow Automation
1. **Attendance:** punch ingestion (web + device endpoint), daily aggregator worker, calendar/history UI, corrections workflow (≤7-day window) + approvals.
2. **Leave:** types/policies, requests + per-day expansion, balance read-model + accrual ledger + accrual worker, approvals, calendar reconciliation, balances UI.
3. **Notifications:** templates, fan-out, per-channel delivery (in-app + email; push/SMS if providers chosen), preferences, inbox/drawer/center, outbound worker + retries.
4. **Scheduler:** wire attendance close, report lock, accruals, retention jobs.

### Phase 4 — Analytics
1. Read-replica routing; analytics endpoints; Analytics screen (stacked/donut, burn, on-time, heatmap, KPIs); async CSV/PDF exports to object storage; materialized views if needed.

### Phase 5 — Enterprise
1. Audit-log UI + search, retention/partition automation, archival.
2. SSO/SAML hardening (multi-provider), MFA, provisioning.
3. Multi-tenancy (if U-010 = yes) — `tenant_id` + RLS.
4. Mobile/field client + device onboarding; compliance posture; backup/DR drills; billing (if U-008 confirmed).

### Phase 6 — AI / Agentic
1. Assisted report drafting; anomaly detection → notifications; NL analytics; agentic review triage — all human-in-the-loop and audited.

---

## 3. Cross-cutting guardrails (apply from day one)

- **Brand isolation:** product name only in `PRODUCT_NAME` / `--product-name`.
- **Audit everything:** no state change without an audit row; transactions always set `current_user_id`.
- **Deny-by-default authorization;** row-level scoping via org/project.
- **Forward-only validated migrations;** `CONCURRENTLY` + batched backfills for large tables.
- **Read/write split:** analytics off the primary.
- **Idempotent ingestion & dispatch;** dead-letter on poison.
- **Voice:** all user-facing copy is calm, specific, sentence-case (no cheerleading).
- **Definition of done per unit:** tests (unit + integration/contract), audit coverage, error states, a11y pass on UI, docs/OpenAPI updated.

---

## 4. Test & quality strategy (proposed)

- **Backend:** unit (domain logic, state machines, balance math), integration (DB + workers), contract (OpenAPI), security (authz scopes, rate limits).
- **Frontend:** component tests, journey/e2e for the key flows (`frontenddesign.md` §4), accessibility checks (WCAG 2.1 AA).
- **Data:** balance-rebuild and attendance-materialization correctness suites; migration up/down checks.

---

## 5. Immediate next steps (pending approval)

1. Approve this documentation set and plan.
2. Answer the blocking decisions (§1).
3. On approval, begin **Phase 1 step 1** (repo scaffold) — and only then.

_Related: [`roadmap.md`](./roadmap.md) · [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) · [`decisions.md`](./decisions.md)._
