# Project Structure (proposed)

> **Purpose:** the ideal repository/folder layout for the platform. **No code is generated** — this is the target skeleton to be created at the start of Phase 1, after the open decisions (esp. backend stack U-001 and multi-tenancy U-010) are resolved.
>
> **Brand- & stack-agnostic.** No product name appears in any path. Backend internals are organized by **domain module** (the boundaries in `architecture.md` §7) so they survive a stack choice and a later service extraction. Stack-specific file extensions are intentionally omitted.

---

## Top level

```
/                           # repo root (working codename: coreops)
├── README.md               # project overview, quickstart, links to /docs
├── .gitignore
├── docs/                   # ← single source of truth (this documentation set)
├── design-assets/          # imported source material (read-only reference; not built)
├── backend/                # application service + workers (see below)
├── frontend/               # web client (see below)
├── database/               # schema, migrations, seeds (promoted from design-assets/schema)
├── docker/                 # containerization & local orchestration
└── scripts/                # dev/ops/CI helper scripts
```

> `database/` is introduced to give the schema a first-class home outside the read-only `design-assets/`. The existing empty `backend/`, `frontend/`, `docker/`, `scripts/` dirs are the agreed scaffolding targets.

---

## docs/

```
docs/
├── README.md                       # documentation index
├── architecture.md
├── frontenddesign.md
├── backenddesign.md
├── databasedesign.md
├── roadmap.md
├── decisions.md                    # decided / assumptions / unresolved
├── documentation-review-report.md
├── PROJECT_STRUCTURE.md            # this file
└── implementation-plan.md
```

---

## backend/  (modular monolith; modules extractable later)

```
backend/
├── src/
│   ├── platform/                   # cross-cutting framework code
│   │   ├── config/                 # incl. PRODUCT_NAME (single brand source)
│   │   ├── http/                   # server, routing, middleware
│   │   ├── auth-context/           # sets current_user_id GUC per request
│   │   ├── rbac/                   # permission + scope evaluation
│   │   ├── audit/                  # audit-log writer / log_event
│   │   ├── db/                     # connection, tx helpers, replica routing
│   │   ├── queue/                  # broker abstraction, outbox
│   │   ├── errors/                 # uniform error envelope
│   │   └── observability/          # logging, metrics, tracing
│   ├── modules/                    # ← domain modules (architecture.md §7)
│   │   ├── identity-access/        # auth_users, sessions, roles, permissions
│   │   ├── org-people/             # employees, departments, locations, shifts
│   │   ├── projects/
│   │   ├── daily-reporting/
│   │   ├── attendance/
│   │   ├── leave/
│   │   ├── notifications/
│   │   └── analytics/              # read-only, replica-backed
│   │       # each module: api/ (routes), domain/ (logic, state machines),
│   │       #             data/ (repositories), events/ (emit/consume)
│   ├── workers/                    # async jobs (backenddesign.md §5)
│   │   ├── notification-dispatch/
│   │   ├── attendance-aggregator/
│   │   ├── report-locker/
│   │   ├── leave-accrual/
│   │   ├── audit-retention/
│   │   └── export-builder/
│   └── scheduler/                  # cron wiring (or pg_cron definitions)
├── tests/                          # unit / integration / contract
└── openapi/                        # API contract (to author — G2)
```

## frontend/  (web client)

```
frontend/
├── src/
│   ├── app/                        # shell, routing, providers
│   ├── design-system/
│   │   ├── tokens/                 # colors_and_type (recover/re-author — U-005)
│   │   ├── primitives/             # Button, Card, Badge, Avatar, Field, Table, Modal…
│   │   ├── charts/                 # WeekChart, StackedBars, Donut, Burn, Heatmap…
│   │   └── brand/                  # Brand component + --product-name (single name source)
│   ├── features/                   # one folder per screen (frontenddesign.md §3)
│   │   ├── auth/                   # Login + flows
│   │   ├── dashboard/
│   │   ├── daily-report/
│   │   ├── report-history/
│   │   ├── attendance/
│   │   ├── team/
│   │   ├── analytics/
│   │   ├── admin/
│   │   ├── project-detail/
│   │   └── notifications/
│   ├── lib/                        # api client, query layer, auth context, hooks
│   └── styles/
├── public/                         # logo-mark.svg, logo-wordmark.svg, favicon
└── tests/
```

## database/

```
database/
├── schema/          # current DDL (promoted from design-assets/schema, identifiers neutralized)
├── migrations/      # forward-only, versioned (databasedesign.md §11)
├── seeds/           # reference data: roles, permissions, leave_types, activity_types, notification_templates
└── jobs/            # scheduled-job definitions (pg_cron or external)
```

## docker/ & scripts/

```
docker/
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml      # local: app + postgres + queue + object-store emulator
└── ...

scripts/
├── bootstrap/              # local setup
├── ci/                     # lint, test, build, migrate
└── ops/                    # backup, partition pre-create, retention runners
```

---

## Structural principles

1. **One brand source each side** — `backend/src/platform/config` (`PRODUCT_NAME`) and `frontend/src/design-system/brand` (`--product-name`). Nothing else names the product (D-001).
2. **Module isolation** — modules talk via events/interfaces, not by reaching into each other's `data/`; this is what makes the Phase-5 service extraction cheap.
3. **Read/write split** — `analytics` is read-only and replica-backed; never on the OLTP write path.
4. **Workers are first-class** — async work is not buried in request handlers (matches the schema's scheduled-job + outbound-queue design).
5. **Contract-first** — `openapi/` is authored before frontend integration (closes gap G2).
6. **`design-assets/` stays read-only** — source material, never imported by build; the schema is promoted into `database/` when neutralized.

_Related: [`architecture.md`](./architecture.md) · [`backenddesign.md`](./backenddesign.md) · [`frontenddesign.md`](./frontenddesign.md) · [`implementation-plan.md`](./implementation-plan.md)._
