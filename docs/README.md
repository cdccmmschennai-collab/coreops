# Documentation Index

This `docs/` directory is the **single source of truth** for the platform (working codename: **CoreOps**). It was produced by consolidating everything under `design-assets/` (database schema, hi-fi UI kit, design-system deck, brand assets, screenshots).

> **Naming:** the product has **no final name**. Docs are brand-agnostic ("the platform"). *CoreOps* = working codename, *WorkTrack* = design-system reference, *Cadence* = legacy. See the [Naming Decision Record](./architecture.md#14-naming-decision-record).
>
> **No code yet.** Implementation is gated on approval of this set — see [`implementation-plan.md`](./implementation-plan.md).

## Read in this order

| # | Document | What it covers |
|---|---|---|
| 1 | [documentation-review-report.md](./documentation-review-report.md) | Asset inventory, duplicates, outdated material, conflicts, gaps — start here |
| 2 | [architecture.md](./architecture.md) | Vision, problem, goals, personas, context, high-level architecture, boundaries, deployment, security, scalability, observability, future, **Naming Decision Record**, glossary |
| 3 | [databasedesign.md](./databasedesign.md) | ERD, entities, relationships, indexing, partitioning, audit, tenancy, retention, backup, migration, scaling (authoritative DB ref) |
| 4 | [backenddesign.md](./backenddesign.md) | Service architecture, API surface, domain model, modules, workers/queue, authn/authz, audit, observability, errors, rate limiting, security, future decomposition |
| 5 | [frontenddesign.md](./frontenddesign.md) | Design system (tokens/type/motion/voice), components, pages, journeys, navigation, state, API consumption, errors, accessibility, responsive, future |
| 6 | [roadmap.md](./roadmap.md) | Phases 0–6 (objectives, deliverables, risks, dependencies, success criteria) |
| 7 | [decisions.md](./decisions.md) | **Decided** ADRs · **Assumptions** · **Unresolved decisions** (three registers) |
| 8 | [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) | Ideal repository/folder structure (no code) |
| 9 | [implementation-plan.md](./implementation-plan.md) | Ordered, reviewable build plan + approval gate |

### Domain Modeling phase

| # | Document | What it covers |
|---|---|---|
| 10 | [DOMAIN_MODEL.md](./DOMAIN_MODEL.md) | Bounded contexts, aggregates, entities, value objects, domain events, relationships (context map) |
| 11 | [USER_ROLES_AND_PERMISSIONS.md](./USER_ROLES_AND_PERMISSIONS.md) | 7 roles (Super Admin → Viewer), permission catalog, detailed permission matrix |
| 12 | [WORKFLOWS.md](./WORKFLOWS.md) | Attendance (check-in/punch/break/check-out), reporting, project, recruitment, approval, notification workflows |
| 13 | [TENANCY_STRATEGY.md](./TENANCY_STRATEGY.md) | Single vs multi-tenant comparison + recommendation (`tenant_id`+RLS) |
| 14 | [INTEGRATIONS.md](./INTEGRATIONS.md) | Biometric, Email, WhatsApp, SMS, LDAP/AD, Google Workspace, M365 |
| 15 | [EVENT_ARCHITECTURE.md](./EVENT_ARCHITECTURE.md) | Event-driven backbone: catalog, envelope, outbox, consumption semantics |
| 16 | [AI_ROADMAP.md](./AI_ROADMAP.md) | Anomaly detection, missing reports, project risk, recruitment insights, exec summaries, agentic automation |
| 17 | [IMPLEMENTATION_SEQUENCE.md](./IMPLEMENTATION_SEQUENCE.md) | Safest dependency-ordered build sequence (S0–S13) |

### v1 build (scoped, on existing stack)

| # | Document | What it covers |
|---|---|---|
| 18 | [V1_IMPLEMENTATION_PLAN.md](./V1_IMPLEMENTATION_PLAN.md) | v1 scope validation, minimal roadmap, structures, port isolation from SPIR, dev & test sequences |
| 19 | [V1_ARCHITECTURE_PACKAGE.md](./V1_ARCHITECTURE_PACKAGE.md) | **FROZEN build spec.** Resolved decisions, final DB schema, route/module maps, permission matrix, git + Docker architecture, migration plan |
| 20 | [api/openapi-v1.yaml](./api/openapi-v1.yaml) | OpenAPI 3.1 contract of record for v1 (auth, users, employees, attendance, projects, reports, dashboard) |
| 21 | [V0_FOUNDATIONS_REPORT.md](./V0_FOUNDATIONS_REPORT.md) | V0 build report: files created, security review, env vars, Docker, startup |
| 22 | [V0_AUDIT_REPORT.md](./V0_AUDIT_REPORT.md) | Architecture/implementation audit of V0 (10 areas, findings F1–F12, verdict) |
| 23 | [V1_AUTHENTICATION_PLAN.md](./V1_AUTHENTICATION_PLAN.md) | V1 auth plan: JWT, login/logout, current-user, role enforcement, hashing, admin bootstrap |
| 24 | [V1_AUTHENTICATION_REPORT.md](./V1_AUTHENTICATION_REPORT.md) | V1 auth completion report: steps, decisions, 25 tests, e2e smoke, endpoints |

### Frontend architecture & UX review (pre-build, no code)

| # | Document | What it covers |
|---|---|---|
| 25 | [FRONTEND_ARCHITECTURE.md](./FRONTEND_ARCHITECTURE.md) | Rendering strategy, folder structure, state (React Query), auth/token handling, RBAC on client, V0 validation, open decisions FD-1..4 |
| 26 | [FRONTEND_DESIGN_SYSTEM.md](./FRONTEND_DESIGN_SYSTEM.md) | Tokens (color/type/spacing/radii/shadow/motion), component catalog + states, status mapping, voice, a11y |
| 27 | [FRONTEND_ROUTE_MAP.md](./FRONTEND_ROUTE_MAP.md) | Route tree, layouts/groups, guards, role visibility matrix, URL-state, redirects |
| 28 | [DASHBOARD_SCREEN_SPEC.md](./DASHBOARD_SCREEN_SPEC.md) | Dashboard spec + ASCII wireframes (desktop/mobile) |
| 29 | [EMPLOYEES_SCREEN_SPEC.md](./EMPLOYEES_SCREEN_SPEC.md) | Employees list/detail spec + wireframes |
| 30 | [PROJECTS_SCREEN_SPEC.md](./PROJECTS_SCREEN_SPEC.md) | Projects list/detail spec + wireframes |
| 31 | [ATTENDANCE_SCREEN_SPEC.md](./ATTENDANCE_SCREEN_SPEC.md) | Attendance calendar/history/team spec + wireframes |
| 32 | [REPORTS_SCREEN_SPEC.md](./REPORTS_SCREEN_SPEC.md) | Reports list/new/detail-review spec + wireframes |
| 33 | [SETTINGS_SCREEN_SPEC.md](./SETTINGS_SCREEN_SPEC.md) | Settings (profile/security/users & roles) spec + wireframes + API gap FD-3 |
| 34 | [FRONTEND_IMPLEMENTATION_PLAN.md](./FRONTEND_IMPLEMENTATION_PLAN.md) | **Build roadmap.** Stack (Tailwind/shadcn/TanStack/RHF/Zod), folder structure, state, API client, auth flow, page & component build order, testing, phases F0–F8 |
| 35 | [FRONTEND_F0_F1_REPORT.md](./FRONTEND_F0_F1_REPORT.md) | F0+F1 completion report: files, dependencies, routes, verification, remaining work |
| 36 | [V2_EMPLOYEES_REPORT.md](./V2_EMPLOYEES_REPORT.md) | V2 employees backend: model, migration, endpoints, RBAC, 43 tests, verification |
| 37 | [FRONTEND_F4_EMPLOYEES_REPORT.md](./FRONTEND_F4_EMPLOYEES_REPORT.md) | F4 employees frontend: contract-typed data layer, list/detail/create/edit/deactivate, verification |
| 38 | [V3_PROJECTS_PLAN.md](./V3_PROJECTS_PLAN.md) | V3 projects backend plan: domain, schema, membership, RBAC, API/OpenAPI, validation, service, migration, tests, FE/Attendance/Reports implications |
| 39 | [FRONTEND_F5_PROJECTS_REPORT.md](./FRONTEND_F5_PROJECTS_REPORT.md) | F5 projects frontend: contract-typed data layer, list/detail/create/edit/archive, member assignment, verification |

## Conventions
- _(proposed)_ = design intent, not built. _(assumed)_ = taken as true, unconfirmed.
- Open questions are tracked as **U-0xx**, assumptions as **A-0xx**, decisions as **D-0xx** in `decisions.md`.
- `design-assets/` is **read-only source material** and is not built.
