# CoreOps — Documentation Review Report

**Date:** 2026-05-30
**Author:** Principal Software Architect (design-asset consolidation pass)
**Scope:** Full read and categorization of everything under `design-assets/`, conversion into the canonical documentation set under `docs/`.
**Status:** Documentation pass only. No implementation code written; `backend/`, `frontend/`, `docker/`, `scripts/` left untouched (all are currently empty).

---

## 1. Purpose

CoreOps imported a large body of pre-existing design material (database schema, a hi-fi UI kit, a design-system deck, screenshots, brand assets, and scraps). This report inventories that material, classifies it, identifies duplication / drift / conflicts / gaps, and records how it was folded into the six canonical documents. From this point on, the files under `docs/` are the **single source of truth**; the `design-assets/` tree is treated as source material, not as authority.

---

## 2. Asset inventory & categorization

| Category | Assets | Fidelity | Disposition |
|---|---|---|---|
| **Database design** | `design-assets/schema/*.sql` (9 modules + `00_setup` + `apply_all`), `schema/README.md` | Production-grade, internally consistent | **Authoritative.** Folded into `docs/database-design.md`. |
| **Frontend / UI implementation** | `ui_kits/web_app/` — `index.html`, `app.css`, `components.jsx`, `shell.jsx`, `toasts.jsx`, `README.md`, `screens/*.jsx` (10 screens) | Hi-fi click-through prototype (React + Babel via CDN) | **Authoritative for UX/IA.** Folded into `docs/frontend-design.md`. Prototype only — not production code. |
| **Design system / brand** | `deck/Design System Overview.html`, `deck/deck-stage.js`, `assets/brand/Fonts.pdf`, `assets/brand/font-system.png`, `assets/logo-mark.svg`, `assets/logo-wordmark.svg`, `preview/*.html` (30 token demos), `preview/_card.css` | High | **Authoritative for tokens/voice.** Folded into `docs/frontend-design.md` (§ Design System). |
| **Screenshots** | `screenshots/*.png` (6 files) | Reference renders | **Partially outdated** — see §4. Used to validate the prototype; the Cadence-era shots are superseded. |
| **Scraps** | `scraps/sketch-2026-05-25T...napkin` | Doodle (single brush stroke, no semantic content) | **Discarded** — no extractable requirement. Recorded here for completeness. |
| **Repo scaffolding** | `backend/`, `frontend/`, `docker/`, `scripts/` (empty), `README.md` (empty), `.gitignore` (empty) | — | Untouched per instructions. |

### Module coverage of the DB schema
`00_setup` (extensions, enums, audit triggers) · `01_auth_rbac` · `02_employees` (locations/departments/shifts/employees/history) · `03_projects` (activity types/projects/members) · `04_daily_reports` (+entries/history/mentions) · `05_attendance` (records/punches/corrections/holidays) · `06_leave` (types/balances/accruals/requests/days) · `07_notifications` (templates/notifications/recipients/preferences) · `08_audit` (monthly-partitioned audit log) · `09_indexes_views` (soft-delete views, recursive org view, dashboard views, retention helpers).

### Screen coverage of the UI kit
`Login` · `Dashboard` (employee home) · `ReportForm` (daily report) · `History` (my reports) · `Attendance` (calendar/history/balances/corrections) · `Team` (manager) · `Analytics` · `Admin` (people/projects/roles/leave/corrections/audit/SSO) · `ProjectDetail` · `Notifications` (center + drawer).

---

## 3. Duplicates

| # | Finding | Detail | Action |
|---|---|---|---|
| D1 | **Three byte-identical screenshots** | `02-dashboard-worktrack.png`, `03-dashboard-tall.png`, `04-dashboard-v2.png` share MD5 `9f8edb27…`. The names imply three variants ("tall", "v2") but the files are the same image. | Keep one (`02`). The "tall"/"v2" names are misleading and should be deleted to avoid implying variants that don't exist. |
| D2 | **Dashboard rendered twice in two media** | The deck's slide 05 ("The system, assembled") and `screens/Dashboard.jsx` render the same dashboard. | Not a conflict — intentional. `Dashboard.jsx` is the authoritative source; the deck slide is a static echo. |
| D3 | **`v_manager_review_queue` vs review-queue index** | `09_indexes_views.sql` defines a view that overlaps the `daily_reports_review_queue_idx` partial index in `04`. | Both intentional (view for reads, index for performance). Documented together in `database-design.md`. |

---

## 4. Outdated material

| # | Finding | Detail | Action |
|---|---|---|---|
| O1 | **Cadence-era brand screenshots** | `01-dashboard.png` and `01-dashboard-full.png` show the **"Cadence"** wordmark with a "C" mark. The later brand is **WorkTrack** (bar-chart mark), shown in `02` and `05-dashboard-hq.png`. | Cadence shots are superseded (legacy). WorkTrack is the design-system reference. Neither is treated as the final product name (see §5/C1). |
| O2 | **Early sidebar layout bug** | In `01-dashboard.png` / `01-dashboard-full.png` the sidebar nav labels overlap/wrap ("Today's report" / "My reports" / "Projects" collide). `02` and `05` show the corrected, clean rail. | The corrected layout (matching `shell.jsx`) is canonical. The buggy render is historical. |
| O3 | **`05-dashboard-hq.png` is the canonical reference render** | Highest fidelity, correct brand, serif H1, populated data. | Treat `05` as the reference comp for the dashboard. |

---

## 5. Conflicts & inconsistencies (require resolution)

| # | Conflict | Where | Resolution |
|---|---|---|---|
| **C1** | **Product name: CoreOps vs WorkTrack vs Cadence** | Repo = `coreops`; schema namespace + deck + UI README + most screens = `WorkTrack`; `01-*` screenshots + `Login.jsx` email `priya@cadence.work` + `app.css` header comment = `Cadence`. | **DECIDED (working policy):** No final product name is assumed. **CoreOps** = repository/working codename (a placeholder only). **WorkTrack** = design-system reference. **Cadence** = legacy naming. All documentation is written **brand-agnostic** ("the platform"); the codename carries no architectural weight and can be swapped later. See the **Naming Decision Record** in `architecture.md` and `decisions.md` (D-001). |
| **C2** | **Report locking rule** | `ReportForm.jsx` footer says *"Reports lock at midnight. You can edit submitted reports for 24 hours."* `schema/README.md` scheduled job says *"lock submitted daily reports older than 24h."* Midnight lock and +24h edit window are different rules. | Open. Recorded as unresolved decision in `decisions.md` (U-002). Schema field `daily_reports.locked_at` supports either; the business rule must be pinned down. |
| **C3** | **Email domain drift** | `Login.jsx` seeds `priya@cadence.work`; `Team.jsx` / `Admin.jsx` use `@worktrack.app`. | Cosmetic prototype seed data. Will standardize on the chosen production domain. Flagged, low priority. |
| **C4** | **Typography scale numbers** | Deck type slide shows display sizes (e.g. H1 at 72px) but the **spec column** says `40 / 700`. `app.css` renders page `h1` at 32px serif (which maps to the **H2** token, not H1). | The **spec column** values are canonical (H1 40/700, H2 32/600, …). Rendered slide sizes are presentation scaling. Documented in `frontend-design.md`. |
| **C5** | **"mono" semantics** | `app.css` `.mono` uses **Inter** with `tabular-nums` (not a true monospace), with a comment that real monospace (Geist Mono) is reserved for code/version strings. Chart SVGs hard-code `"Geist Mono, monospace"`. | Documented rule: numeric/tabular data → Inter `tnum`; code/IDs/version strings → Geist Mono (`--font-mono`). |
| **C6** | **`Login.jsx` uses undeclared `mode` state** | The component reads `mode` and calls `setMode(...)` but never declares `useState` for it. | Prototype bug. Noted; irrelevant to production design intent (sign-in / forgot-password / sent states are the requirement). |

---

## 6. Missing requirements & gaps

| # | Gap | Impact | Tracked in |
|---|---|---|---|
| **G1** | **Backend technology stack is entirely unspecified.** No language, framework, or API style (REST vs GraphQL) is declared anywhere. The DB is PostgreSQL 14+; everything above it is undefined. | Blocks `backend-design.md` from being prescriptive. | `decisions.md` U-001; `backend-design.md` documents the *contract* and proposes a stack as an assumption. |
| **G2** | **No API contract / OpenAPI spec.** API surface is only *inferable* from screens + schema. | Frontend/backend integration undefined. | `backend-design.md` (derived API surface). |
| **G3** | **`colors_and_type.css` token file is missing.** `app.css`, the deck, and `preview/*.html` all `@import`/link `../colors_and_type.css` (or `../../`), but the file does not exist in the import. All `--blue-600`, `--radius-*`, `--shadow-*`, `--ease-out`, `--sidebar-w`, etc. are referenced but undefined in-tree. | Token *values* (radii px, shadow stacks, durations) are not authoritative anywhere; reconstructed approximately from the deck + usage. | `frontend-design.md` (token table with reconstructed values + TBD flags); `decisions.md` U-005. |
| **G4** | **Mobile UI kit absent.** The folder is `ui_kits/` (plural) with only `web_app/`; `punch_source` enum includes `mobile`; the marketing copy implies field/mobile use. No mobile screens exist. | Mobile scope undefined. | `roadmap.md` (out-of-scope / later phase); `decisions.md` U-006. |
| **G5** | **Notification delivery infrastructure undefined.** Schema models channels (`in_app`, `email`, `push`, `sms`), retries, and an outbound queue, but no provider/transport is specified. | Email/push/SMS integration unplanned. | `backend-design.md` (notifications service); `roadmap.md`. |
| **G6** | **Domain glossary for report counts.** Daily-report entries carry `Tags / Docs / BOM / Spares / Tasks` counts — `BOM` (bill of materials) and `Spares` strongly imply an engineering/manufacturing-operations domain, not generic SaaS. The meaning of each count is undocumented. | Risk of misimplementing core domain semantics. | `decisions.md` U-007; `database-design.md` notes the fields; glossary stub in `architecture.md`. |
| **G7** | **File/object storage unspecified.** `proof_url`, `photo_url`, exports (CSV/PDF), and `audit_logs` archive URIs imply object storage; none chosen. | Uploads/exports/archival unplanned. | `backend-design.md`; `decisions.md`. |
| **G8** | **Global search (⌘K) backend undefined.** UI shows a command-palette search over "reports, people". Schema notes `pg_trgm` for name search but no search service. | Search feature unscoped. | `backend-design.md`; `roadmap.md`. |
| **G9** | **Latent/unwired features.** `Admin.jsx` defines a `BillingTab` (seats, plan, invoices) that is **not** in the tab list. SSO is "Okta/SAML" in UI but schema also supports `google`/`azure_ad`. | Billing scope ambiguous; SSO providers list needs confirming. | `decisions.md` U-008. |
| **G10** | **Attendance correction window** | UI states corrections allowed "up to 7 days back"; schema has no 7-day CHECK. | Business rule must be enforced in application layer. | `backend-design.md` (workflow rules). |
| **G11** | **Non-functional baselines** — no stated SLAs, scale targets (employee count), or environments (dev/stage/prod). Login panel claims "SOC 2". | Compliance/scale targets unanchored. | `architecture.md` (NFR section, marked assumed). |
| **G12** | **CI/CD, testing strategy, IaC** — `docker/`, `scripts/` empty; no pipeline defined. | Delivery process unplanned. | `roadmap.md` (Phase 0). |

---

## 7. What was produced

The following canonical documents were created from this material (filenames per the program lead's specification):

1. `docs/architecture.md` — vision, problem statement, business goals, personas, system context, high-level architecture, service boundaries, deployment, security, scalability, observability, future expansion, **Naming Decision Record**, glossary.
2. `docs/backenddesign.md` — service architecture, derived API structure, domain model, business modules, worker/queue architecture, authn/authz, audit, observability, error handling, rate limiting, security controls, future decomposition — **with stack marked as an open decision.**
3. `docs/frontenddesign.md` — UI/page inventory, user journeys, navigation, component library, state management, API consumption, error handling, accessibility, responsive strategy, design system (tokens/type/motion/voice), future roadmap.
4. `docs/databasedesign.md` — ERD interpretation, entity definitions, relationships, indexing, partitioning, audit tables, tenant design, retention, backup, migration, future scaling.
5. `docs/roadmap.md` — Phases 0–6 (objectives, deliverables, risks, dependencies, success criteria).
6. `docs/decisions.md` — decided ADRs, **assumptions (separate section)**, and **unresolved decisions (separate section)**.

Phase 2 deliverables:
7. `docs/PROJECT_STRUCTURE.md` — ideal repository/folder structure (no code).
8. `docs/implementation-plan.md` — staged implementation plan, pending approval before any coding.

Plus `docs/README.md` as the documentation index.

> **Brand-agnostic policy:** documentation refers to **"the platform"**; where a name is unavoidable, **CoreOps** is used purely as a working codename and is isolated to a single configurable identifier so the final product name can be set later with minimal change.

> **Preservation guarantee:** every substantive statement in the source `schema/README.md`, the deck, and the UI kit README was carried into the docs above. Nothing useful was dropped; the napkin scrap (D-discard) was the only asset with no extractable content.
