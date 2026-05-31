# Tenancy Strategy

> **Phase:** Domain Modeling (no code). Brand-agnostic. Resolves the open question `decisions.md` **U-010** with a recommendation. The current schema (`databasedesign.md` §8) is **single-tenant** — there is no `tenant_id` anywhere.
>
> **Why this matters now:** tenancy touches **every table, index, query, and RBAC scope**. Retrofitting it after data exists is expensive and risky. It must be decided **before Phase 1 entities are built**.

---

## 1. The choice

| | **Single-Tenant** | **Multi-Tenant (shared schema)** | **Multi-Tenant (schema/DB per tenant)** |
|---|---|---|---|
| Isolation | Whole deployment = 1 org | Logical via `tenant_id` + RLS | Physical via separate schema/DB |
| Data model | As-is | `tenant_id` on every entity | Same model, replicated per tenant |
| Noisy-neighbor risk | None | Yes (shared resources) | Low |
| Per-tenant customization | Trivial | Harder (shared) | Easy |
| Onboarding a tenant | New deploy | Insert a row | Provision schema/DB + migrate |
| Migration cost (N tenants) | 1 | 1 (shared) | N (fan-out) |
| Cross-tenant analytics | N/A | Easy (one DB) | Hard (federate) |
| Blast radius of a bug | 1 org | All orgs | 1 org |
| Ops complexity | Low | Medium | High |
| Cost at scale | High per-org | **Low per-org** | Medium–High |
| Compliance/residency | Strong (dedicated) | Needs RLS rigor | Strong |

---

## 2. Analysis

**Single-Tenant** fits **self-hosted / on-prem enterprise** sales (each customer runs their own instance). It is the simplest path and matches today's schema exactly — but it does not scale as a SaaS (per-org infra cost, N deployments to operate and patch).

**Multi-Tenant shared-schema (`tenant_id` + Postgres Row-Level Security)** is the standard SaaS model: one database, one codebase, a `tenant_id` discriminator on every row, and RLS policies that make tenant isolation a property of the database rather than of application discipline. Cheapest per-org, easiest to operate and to do cross-tenant analytics. The cost is **rigor**: every table, every unique index, and every RBAC scope must include `tenant_id`, and RLS must be enforced (defense in depth behind app-level scoping).

**Schema/DB-per-tenant** gives the strongest isolation and easy per-tenant customization/residency, at the price of N-way migrations and heavier ops. It suits a **small number of large, isolation-sensitive** tenants.

---

## 3. Recommendation

**Primary recommendation: Multi-Tenant, shared-schema with `tenant_id` + RLS** — *if the product is SaaS* (the most likely target given SSO/enterprise framing).

- Add `tenant_id uuid NOT NULL` to **every tenant-owned table**; include it as the **leading column** of every unique index and every "list view" composite index.
- Enforce **Row-Level Security** policies keyed off a per-request GUC (extend the existing `current_user_id` pattern with `app.current_tenant_id`), so isolation holds even if an application query forgets the filter.
- Make RBAC scopes **tenant-relative** (a `global` scope means global *within the tenant*; only `super_admin` may operate cross-tenant, and only via explicit, audited operations).
- Keep the **audit log partitioned by month** but **include `tenant_id`** for per-tenant export/retention.
- Shared lookup/reference data (e.g. system roles, default notification templates) can be **tenant-null = global defaults**, overridable per tenant.

**Fallback:** if the go-to-market is **single-tenant / self-hosted per customer**, keep the schema as-is and treat "tenant" as the deployment. Provide a clean migration path to shared-schema later **only if** you accept a one-time backfill.

**Hybrid option:** shared-schema for the long tail + **dedicated DB for marquee/regulated tenants** (same codebase, routed by tenant). Defer unless a customer requires it.

> **Decision gate:** confirm SaaS vs self-hosted with the business **before Phase 1**. If SaaS, introduce `tenant_id` + RLS as the *first* schema change (it cannot be cheaply added later).

---

## 4. Implementation implications (when multi-tenant)

| Area | Change |
|---|---|
| Schema | `tenant_id` on all entity tables; leading column in unique + list indexes; FK to a `tenants` table |
| RLS | `ENABLE ROW LEVEL SECURITY` + `USING (tenant_id = current_setting('app.current_tenant_id')::uuid)` per table |
| App | Resolve tenant from auth/session at the edge; `SET LOCAL app.current_tenant_id` alongside `current_user_id` |
| RBAC | Scopes evaluated within tenant; `super_admin` cross-tenant ops explicit + audited |
| Integrations | Per-tenant integration config (SSO, biometric devices, mail/WhatsApp senders) — see `INTEGRATIONS.md` |
| Events | `tenant_id` in every event envelope (`EVENT_ARCHITECTURE.md`) |
| Analytics | Tenant-scoped read models; replica routing unchanged |
| Backup/retention | Per-tenant export & deletion honoring residency |

## 5. Open items
- **U-010** (this doc resolves the *recommendation*; business must confirm SaaS vs self-hosted).
- Data-residency requirements (drives hybrid/dedicated-DB need) — fold into `U-012` (NFRs).
- Per-tenant configurability scope (templates, roles, branding `--product-name`) — naturally fits multi-tenant + the brand-agnostic policy (D-001).

_Related: [`databasedesign.md`](./databasedesign.md) §7 · [`architecture.md`](./architecture.md) §13 · [`decisions.md`](./decisions.md) U-010._
