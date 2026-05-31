# User Roles & Permissions

> **Phase:** Domain Modeling (no code). Brand-agnostic. Extends the RBAC model in `databasedesign.md` §3.1 and `backenddesign.md` §8.
>
> **Role expansion (D-014):** the existing schema ships five role keys (`admin`, `manager`, `employee`, `hr`, `viewer`). This phase introduces the enterprise role set below. **`super_admin`, `team_lead`, `recruiter` are new** and require seed rows in `roles` + grants in `role_permissions`. `hr` is retained as an internal capability set folded into Admin/Recruiter where appropriate. Recorded in `decisions.md` D-014.

---

## 1. Roles

| Role | `roles.key` | Default scope | Essence |
|---|---|---|---|
| **Super Admin** | `super_admin` | `global` | Platform owner. Everything Admin can do **plus** tenant/SSO/security config, role definition, and (if multi-tenant) cross-tenant operations. The only role that can grant Admin. |
| **Admin** | `admin` | `global` | Workspace administration: people, projects, roles (assign, not redefine system roles), leave/correction approvals, audit log, integrations. |
| **Manager** | `manager` | `department` / `project` | Owns a team/org subtree. Reviews reports, approves leave & corrections, sees team & project analytics for their scope. |
| **Team Lead** | `team_lead` | `project` / sub-team | A scoped manager-lite: reviews reports and sees load for **their team/project only**; cannot approve leave or manage membership beyond their scope. |
| **Recruiter** | `recruiter` | `global` (recruitment) / `department` | Owns the Recruitment context: requisitions, candidates, pipeline, offers. Read-only on People; triggers onboarding handoff on hire. |
| **Employee** | `employee` | `self` | Individual contributor: own reports, attendance, leave, profile, notifications. |
| **Viewer** | `viewer` | `project` / `department` | Read-only stakeholder: project pages and (scoped) analytics. No mutations. |

**Scoping (existing model):** every grant carries a `scope_type` ∈ `global | department | project | self` and a `scope_id`. A person may hold multiple grants (e.g. *Manager of Platform* + *Viewer of Q3 Planning*). Permission checks evaluate **permission key × scope coverage** (org reach via `v_employee_org`, project reach via `project_members`).

---

## 2. Permission keys (catalog)

Dotted keys per the existing convention (`databasedesign.md`). This catalog formalizes the examples in the schema and adds the new contexts. (Finalize as `decisions.md` U-004.)

| Domain | Permission keys |
|---|---|
| Attendance | `attendance.view`, `attendance.punch`, `attendance.correct.request`, `attendance.correct.approve`, `attendance.export` |
| Employee | `employee.view`, `employee.create`, `employee.update`, `employee.deactivate`, `employee.invite` |
| Org | `org.view`, `org.manage` (departments/locations/shifts/holidays) |
| Project | `project.view`, `project.create`, `project.update`, `project.archive`, `project.member.manage` |
| Reporting | `report.view.self`, `report.view.team`, `report.view.all`, `report.submit`, `report.edit`, `report.review`, `report.export` |
| Leave | `leave.view.self`, `leave.view.team`, `leave.request`, `leave.approve`, `leave.policy.manage` |
| Recruitment | `recruit.requisition.manage`, `recruit.candidate.view`, `recruit.candidate.manage`, `recruit.interview.manage`, `recruit.offer.manage`, `recruit.hire.approve` |
| Notifications | `notification.view.self`, `notification.preferences.manage`, `notification.template.manage` |
| Analytics | `analytics.view.self`, `analytics.view.team`, `analytics.view.org`, `analytics.export` |
| Audit | `audit.view`, `audit.export` |
| Admin / Platform | `role.assign`, `role.define`, `sso.manage`, `integration.manage`, `tenant.manage`, `billing.manage` |
| AI | `ai.insights.view`, `ai.agent.approve` |

---

## 3. Permission matrix

Legend: **✓** allowed · **S** allowed **scoped** to own org/team/project · **R** read-only · **—** denied. (Employee actions are implicitly `self`-scoped.)

| Capability | Super Admin | Admin | Manager | Team Lead | Recruiter | Employee | Viewer |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **Attendance — view** | ✓ | ✓ | S | S | — | self | S(R) |
| Attendance — punch (self) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Attendance — request correction | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Attendance — **approve correction** | ✓ | ✓ | S | — | — | — | — |
| Attendance — export | ✓ | ✓ | S | — | — | — | — |
| **Employee — view** | ✓ | ✓ | S | S | R | self | S(R) |
| Employee — create/update | ✓ | ✓ | — | — | — | self(profile) | — |
| Employee — invite | ✓ | ✓ | — | — | — | — | — |
| Employee — deactivate/exit | ✓ | ✓ | — | — | — | — | — |
| **Org — manage** (dept/location/shift/holiday) | ✓ | ✓ | — | — | — | — | — |
| **Project — view** | ✓ | ✓ | S | S | — | S | S(R) |
| Project — create/update/archive | ✓ | ✓ | S(own) | — | — | — | — |
| Project — manage members | ✓ | ✓ | S | S(own) | — | — | — |
| **Report — submit/edit own** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Report — view team/all | ✓ all | ✓ all | S team | S team | — | self | S(R) |
| Report — **review/approve** | ✓ | ✓ | S | S | — | — | — |
| Report — export | ✓ | ✓ | S | — | — | self | — |
| **Leave — request (self)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Leave — **approve** | ✓ | ✓ | S | — | — | — | — |
| Leave — policy manage | ✓ | ✓ | — | — | — | — | — |
| **Recruitment — requisitions** | ✓ | ✓ | R(own dept) | — | ✓ | — | — |
| Recruitment — candidates/pipeline | ✓ | R | R(own dept) | — | ✓ | — | — |
| Recruitment — offers | ✓ | R | — | — | ✓ | — | — |
| Recruitment — **approve hire** | ✓ | ✓ | S(hiring mgr) | — | ✓(req) | — | — |
| **Notifications — own + prefs** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Notification — templates | ✓ | ✓ | — | — | — | — | — |
| **Analytics — view** | ✓ org | ✓ org | S team | S team | S(recruit) | self | S(R) |
| Analytics — export | ✓ | ✓ | S | — | S | — | — |
| **Audit — view/search** | ✓ | ✓ | — | — | — | — | — |
| Audit — export | ✓ | ✓ | — | — | — | — | — |
| **Roles — assign** | ✓ | ✓ (≤ own level) | — | — | — | — | — |
| Roles — **define** (system roles) | ✓ | — | — | — | — | — | — |
| **SSO / integrations** | ✓ | ✓ | — | — | — | — | — |
| **Tenant / billing** | ✓ | R | — | — | — | — | — |
| **AI — view insights** | ✓ | ✓ | S | S | S(recruit) | self | — |
| AI — **approve agent action** | ✓ | ✓ | S | — | S(recruit) | — | — |

---

## 4. Role rules & invariants

1. **Privilege ceiling:** a role may only grant roles **at or below its own level** (Super Admin > Admin > Manager > Team Lead/Recruiter > Employee > Viewer). Only Super Admin grants Admin; only Super Admin can **define/modify system roles** (`roles.is_system_role = true` are immutable to everyone else).
2. **Scope beats role:** holding `manager` does not grant global reach — approvals/reviews are bounded by the grant's scope (`v_employee_org` subtree or project membership). A Team Lead is functionally a Manager whose grants are narrower and **excludes leave/correction approval**.
3. **Separation of duties:** the author of a report/leave/correction cannot approve it; Recruiter cannot self-approve a hire into a requisition they do not own without the hiring manager's approval.
4. **Self by default:** Employee permissions are implicitly `self`. Viewer is strictly read-only (no key ending in a mutating verb).
5. **Recruiter ↔ HR:** the legacy `hr` capability set maps to **Recruiter** (recruitment) + **Admin** (leave policy, people, audit). If a distinct HR persona is needed, model it as Admin-scoped grants rather than a new role.
6. **Every grant is audited** (`RoleGranted`/`RoleRevoked`) and time-boundable (`expires_at`).
7. **Deny-by-default:** absence of a covering grant = 403.

## 5. Mapping to schema
- New role keys → seed rows in `roles` (`super_admin`, `team_lead`, `recruiter`; keep `admin`, `manager`, `employee`, `viewer`).
- Permission keys above → seed rows in `permissions`; role→permission seed in `role_permissions`.
- No schema change needed for scoping — `user_roles.scope_type/scope_id` already supports it.
- Recruitment permissions presuppose the Recruitment tables (U-013).

_Related: [`DOMAIN_MODEL.md`](./DOMAIN_MODEL.md) · [`backenddesign.md`](./backenddesign.md) §8 · [`decisions.md`](./decisions.md) (D-014, U-004, U-013)._
