# Decisions, Assumptions & Open Questions

> Three separate registers, as required:
> - **§A Decided** — choices already made (in the assets, or by the program lead).
> - **§B Assumptions** — things taken as true to make progress, **not yet confirmed**.
> - **§C Unresolved decisions** — open questions that need an owner + answer before/at the relevant phase.
>
> IDs are stable; reference them from the other docs.

---

## §A — Decided (ADRs)

### D-001 — Product name is undecided; CoreOps is a working codename only
**Status:** Decided (program lead, 2026-05-30).
**Context:** Assets carry three names — Cadence (legacy), WorkTrack (design-system reference), CoreOps (repo).
**Decision:** No final product name is assumed. CoreOps = repository/working codename (placeholder, no architectural weight). WorkTrack = design-system reference. Cadence = legacy. All docs are brand-agnostic; the product name lives in **one** config token (`PRODUCT_NAME` / `--product-name`); nothing else hardcodes a name.
**Consequence:** Renaming later = config + asset cleanup, not architecture change. Full record: [`architecture.md` §14](./architecture.md#14-naming-decision-record).

### D-002 — Database engine: PostgreSQL 14+ (16 recommended)
**Status:** Decided (in assets — the schema is production-grade Postgres).
**Decision:** PostgreSQL 14+, using `pgcrypto`, `citext`, `btree_gin`; recommended ops add-ons `pg_stat_statements`, `auto_explain`, `pg_partman`, `pg_cron`.

### D-003 — UUID PKs; bigserial only for append-only logs
**Status:** Decided (schema convention). UUID `gen_random_uuid()` everywhere except `auth_login_attempts` and `audit_logs` (`bigserial`).

### D-004 — Soft delete + partial-unique + live views
**Status:** Decided (schema). `deleted_at` tombstones; uniqueness partial on `deleted_at IS NULL`; read via `v_*` views; hard delete only at retention horizon.

### D-005 — Audit by construction (append-only, partitioned, own schema)
**Status:** Decided (schema). `worktrack_audit.audit_logs` monthly RANGE-partitioned, app `INSERT`-only, archived at 13 months.

### D-006 — Leave balance is a generated read model over an append-only ledger
**Status:** Decided (schema). `leave_balances.current_balance` STORED GENERATED; rebuildable from `leave_accruals` + approved `leave_request_days`.

### D-007 — Attendance is materialized from a raw punch stream
**Status:** Decided (schema). `attendance_punches` (raw, append-only) → `attendance_records` (per-day summary) via a scheduled aggregator; corrections replay onto the record.

### D-008 — Scoped RBAC (role × scope)
**Status:** Decided (schema). `user_roles.scope_type` ∈ {global, department, project, self} + `scope_id`; dotted permission keys.

### D-009 — Polymorphic (non-FK) subject references for notifications & audit
**Status:** Decided (schema). `subject_type/subject_id` and `object_type/object_id` are not FKs so subjects can soft-delete without losing history.

### D-010 — Optimistic concurrency on daily reports
**Status:** Decided (schema). `daily_reports.version` bumped per save; app does compare-and-swap (409 on conflict).

### D-011 — MVP shape: modular monolith with async workers
**Status:** Decided _(recommended in this pass; confirm with stack owner)_. Domain modules in one deployable + worker pool + scheduler; boundaries drawn for later extraction.

### D-012 — Per-request actor GUC for audit/`updated_by`
**Status:** Decided (schema). App sets `SET LOCAL worktrack.current_user_id` (legacy name) per transaction.

### D-013 — Design system: one neutral + one accent + three semantics; Inter/Source Serif 4; calm voice
**Status:** Decided (deck/brand). Tokens, type scale (spec-column values), 120–240ms ease-out motion, sentence-case no-cheerleading voice are authoritative. (Mono = Geist Mono for code/IDs only; numeric data = Inter `tnum`.)

### D-014 — Enterprise role set (role expansion)
**Status:** Decided (Domain Modeling phase, 2026-05-30).
**Decision:** Adopt seven roles — `super_admin`, `admin`, `manager`, `team_lead`, `recruiter`, `employee`, `viewer`. New keys (`super_admin`, `team_lead`, `recruiter`) need seed rows in `roles`/`role_permissions`; no schema change (scoping already supported). Legacy `hr` folds into Admin + Recruiter. Full matrix: [`USER_ROLES_AND_PERMISSIONS.md`](./USER_ROLES_AND_PERMISSIONS.md).

### D-015 — Event-driven backbone via transactional outbox; AI is advisory + human-in-the-loop
**Status:** Decided (Domain Modeling phase). Contexts integrate via past-tense domain events with a uniform envelope, published through a transactional **outbox** (broker optional for MVP — transport is U-017). AI/Insights never mutates domain state directly; it emits insights/suggestions requiring human approval, fully audited. See [`EVENT_ARCHITECTURE.md`](./EVENT_ARCHITECTURE.md), [`AI_ROADMAP.md`](./AI_ROADMAP.md).

### D-016 — Tenancy recommendation
**Status:** Recommended (business confirmation pending — U-010). If SaaS: **multi-tenant shared-schema with `tenant_id` + RLS**, introduced before Phase 1 entities. If self-hosted: single-tenant as-is. See [`TENANCY_STRATEGY.md`](./TENANCY_STRATEGY.md).

---

## §B — Assumptions (unconfirmed; revisit)

| ID | Assumption | Basis | If wrong… |
|---|---|---|---|
| A-001 | 3-tier + async-workers topology; stateless app tier | Standard for this shape; schema implies workers/scheduler | Re-plan deployment (architecture §6/§8) |
| A-002 | Environments: dev → staging → production via CI/CD | Convention; not stated in assets | Adjust Phase 0/1 |
| A-003 | REST + JSON API under `/api/v1` | Inferred from screens; not specified | Re-derive API (could be GraphQL — U-001) |
| A-004 | Object storage exists for proofs/exports/audit archive | Implied by `proof_url`, exports, archive URIs | Add storage decision (G7) |
| A-005 | TLS everywhere; secrets in KMS/secret manager | Security best practice; "SOC 2" claim | N/A (baseline) |
| A-006 | Single-tenant for MVP | No `tenant_id` in schema | See U-010 |
| A-007 | SSO via SAML/OIDC with Okta/Google/Azure AD | Login UI + `sso_provider` values | Confirm provider list (U-008) |
| A-008 | Reconstructed token values (radii/shadow/duration) are approximately correct | Deck + CSS usage; token file missing | Re-author from recovered `colors_and_type.css` (U-005) |
| A-009 | Timezones rendered per `employees.timezone`; storage is `timestamptz` | Schema convention | Confirm i18n/tz rules |
| A-010 | Domain is engineering/manufacturing ops | BOM/Spares/Tags counts | Confirm with domain owner (U-007) |

---

## §C — Unresolved decisions (need an owner + answer)

| ID | Question | Why it matters | Needed by |
|---|---|---|---|
| **U-001** | **Backend technology stack** (language/framework) and **API style** (REST vs GraphQL)? | Blocks all backend implementation; shapes API contract | Phase 1 start |
| **U-002** | **Report locking rule:** "lock at midnight" (UI copy) vs "lock 24h after submission" (schema job)? | Determines edit window + locker worker logic | Phase 2 |
| **U-003** | Final **email/domain** and brand strings (assets mix `@cadence.work` / `@worktrack.app`)? | Cosmetic but pervasive; tied to D-001 | Phase 1 (config) |
| **U-004** | **Permission catalog** — exact list of permission keys + role→permission grants (only examples exist)? | Required to enforce authorization precisely | Phase 1 |
| **U-005** | **Recover or re-author `colors_and_type.css`** (the missing token source)? Exact radii/shadow/duration values. | Pixel-faithful UI + design-token package | Phase 1–2 |
| **U-006** | **Mobile app & device ingestion** scope and protocol (`mobile`/`biometric`/`kiosk` punches)? | No mobile kit exists; ingestion endpoint undefined | Phase 3/5 |
| **U-007** | **Domain semantics of report counts** — what do Tags / Docs / BOM / Spares precisely mean and how are they validated? | Core data correctness; AI features depend on it | Phase 2 |
| **U-008** | **Latent/optional features:** is **Billing** (unwired `BillingTab`) in scope? Confirm **SSO provider** list. | Scope + Admin surface | Phase 5 |
| **U-009** | **Cloud/provider & infra** (hosting, queue broker, mail/push/SMS providers, object storage)? | Deployment, cost, integrations | Phase 1/3 |
| **U-010** | **Multi-tenancy:** single-tenant, or `tenant_id`+RLS / schema-per-tenant? | Touches every table/index; expensive to retrofit | **Before Phase 1 entities** |
| **U-011** | **Search infrastructure** for ⌘K (people/reports) — Postgres `pg_trgm`/FTS vs external search? | Global search feature | Phase 2/4 |
| **U-012** | **Non-functional targets** — scale (employee count), latency SLAs, compliance scope (actual SOC 2?)? | Anchors scalability/observability/compliance work | Phase 1 |
| **U-013** | **Recruitment data model** — the Recruitment bounded context (requisitions/candidates/applications/interviews/offers) has **no schema yet**. | Blocks Recruitment context (S10) | Phase 5 / S10 |
| **U-014** | **Biometric device vendor(s) & protocol** (push/pull/batch) and **template/PII handling**. | Blocks Biometric integration (S7) | Phase 3 / S7 |
| **U-015** | **WhatsApp & SMS providers** (BSP, template governance, opt-in). | Blocks those notification channels | Phase 3 / S8 |
| **U-016** | **Directory sync model** for LDAP/AD, Google Workspace, M365 — JIT vs pre-provision, group→role mapping, SCIM scope. | Blocks enterprise SSO/provisioning | Phase 5 / S12 |
| **U-017** | **Event bus transport** — outbox-only vs broker; which broker; ordering guarantees per stream. | Shapes event-driven backbone | Phase 1 / S0 |
| **U-018** | **AI model hosting & data governance** — managed API vs self-hosted, data egress/PII boundary, per-tenant opt-in, fairness controls. | Blocks AI capabilities (S11/S13) | Phase 6 |

---

## §D — v1 resolutions (frozen for build)

Approved for **Workforce Management System v1** (single-company, single-tenant). Full detail in [`V1_ARCHITECTURE_PACKAGE.md`](./V1_ARCHITECTURE_PACKAGE.md) §2.

| ID | v1 resolution |
|---|---|
| U-001 | FastAPI + REST/JSON `/api/v1` |
| U-002 | Report editable while draft/submitted & unreviewed; hard cutoff at end of `report_date`. No locker worker. |
| U-004 | Single `role` enum (admin/manager/employee/viewer) + manager scoping via `manager_id`. No RBAC tables. |
| U-005 | Re-author minimal `tokens.css` (non-blocking). |
| U-007 | Generic report fields (hours/tasks_done/tasks_open/remarks); domain counts deferred. |
| U-009 | Docker Compose on VPS; email/object-storage deferred. |
| U-010 | Single-tenant; no `tenant_id`. |
| U-011 | `ILIKE` filters only. |
| U-012 | ≤ ~1,000 employees; single DB, no replica/partitioning. |
| U-006, U-013–U-018 | Deferred (mobile, recruitment, biometric, WhatsApp/SMS, directory/SSO, event bus, AI). |
| Auth | Local email+password, JWT bearer; admin resets passwords; logout via Redis denylist. No SSO/MFA. |
| Audit | No `audit_logs` table; `created_by`/`updated_by` + timestamps only. |
| Ports | Frontend 3100 · Backend 8100 · PostgreSQL 5433 · **Redis 6381** (supersedes earlier 6380). |

---

## Cleanup backlog (legacy identifiers — track, action at rename)
- DB schema names `worktrack` / `worktrack_audit` → neutral (e.g. `core` / `audit`).
- GUC `worktrack.current_user_id` → e.g. `app.current_user_id`.
- UI brand strings/marks, seed emails, `app.css` header comment → neutral / `--product-name`.
- Duplicate screenshots `03-dashboard-tall.png` & `04-dashboard-v2.png` (identical to `02`) → delete.
- Cadence-era screenshots `01-dashboard*.png` → archive as historical.
- Prototype bug: `Login.jsx` uses undeclared `mode` state → fix in production build.

---

_Related: [`architecture.md`](./architecture.md) · [`documentation-review-report.md`](./documentation-review-report.md) · [`roadmap.md`](./roadmap.md)._
