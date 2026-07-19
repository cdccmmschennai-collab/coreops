# Full-Day / Split-Day Work Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one Daily Work Report per (employee, date) be filed either as one Full-Day period or as First-Half + Second-Half periods, with per-period status/location/remarks/activities and server-derived benchmark fractions — fully backward compatible with the existing full-day API, data, and UI.

**Architecture:** Additive `work_report_periods` child table under the unchanged `daily_work_reports` header (unique `(employee_id, report_date)` kept). `work_report_tasks` and `activity_requests` gain a nullable `period_id`. Periods are **always maintained internally** once the code ships (every create/update writes them); the `REPORT_DAY_PARTS_ENABLED` / `NEXT_PUBLIC_REPORT_DAY_PARTS_ENABLED` flags gate only whether *split_day* payloads are accepted and whether the UI offers the Day Format selector. Legacy full-day payloads are translated server-side into one Full-Day period. Benchmark math moves from report-wide `half_day` detection to per-task-row `base × period_fraction`, frozen at submit into new `benchmark_base_value_snapshot` / `benchmark_fraction_snapshot` columns beside the existing effective `benchmark_value_snapshot`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (backend, `docker exec wms-backend-1 pytest`), Next.js + react-hook-form + zod + openapi-typescript (frontend).

## Global Constraints (from the approved spec)

- Exactly one `daily_work_reports` header per (employee_id, report_date); the unique constraint `work_reports_emp_date_uq` is never dropped.
- `report_mode ∈ {full_day, split_day}`; `day_part ∈ {full_day, first_half, second_half}`; unique `(report_id, day_part)`.
- Fractions server-derived only: full_day → 1.0, first_half → 0.5, second_half → 0.5. Never client-supplied.
- Full-day mode = exactly one full_day period; split mode = exactly first_half + second_half; full_day part never coexists with halves.
- Non-working period: no activity rows, no benchmark. Working period: ≥ 1 activity at submission.
- One normal primary activity per working period without approval; extras via the existing PM Activity Request flow; Project Meeting / Training / Trainer bypass preserved. (This allowance is enforced where it is today — in the form UI + request flow — the backend keeps its current permissive task validation; see "Deliberate parity decisions".)
- Never edit deployed migrations; new migration `0060` only; additive, no dropped columns, reversible as far as reasonable.
- Historical `half_day` reports: keep effective half benchmark, do NOT guess the half; legacy Full-Day period with `work_fraction = 0.5` + `is_legacy_half_day = true` marker.
- Numeric production benchmarks only are scaled; TASK_BASED deadlines / WorkItem due dates unchanged.
- At submit, freeze: base benchmark, period fraction, effective benchmark, relevant count field, deficit, productivity %.
- Existing full-day API payloads keep working verbatim; all authorization/validation stays server-side.
- PM/Head/Activity-Lead permissions unchanged.
- Attendance not redesigned now; compliance derives fractions and *warns* on mismatch.
- Git: the user commits; the session never runs git mutations (standing instruction).

---

## Current-state map (inspection findings)

| Area | File(s) | Relevant behavior today |
|---|---|---|
| Report header | `backend/app/modules/work_reports/models.py` | `DailyWorkReport` with `day_status` (13-value `day_status` PG enum incl. `half_day`), `location`, `remarks`, unique emp+date. `NO_ACTIVITY_DAY_STATUSES = {leave, company_holiday, week_off, comp_off}`. |
| Task rows | same | `WorkReportTask.report_id` (CASCADE); snapshots incl. `benchmark_value_snapshot` (effective target frozen at submit), `relevant_count_field_snapshot`, `deficit`, `productivity_pct`; TASK_BASED `started_date/due_date`; `work_item_id`. |
| Service | `work_reports/service.py` | Create/update replace all task rows; leave-type day statuses drop tasks; `submit_work_report → _apply_benchmarks` halves NUMERIC targets when `report.day_status == half_day` (report-wide). Head/Lead scoping in `_apply_scope` / `_restrict_to_led_rows` keys off task rows only. |
| Activity requests | `activity_requests/models.py`, `service.py` | `report_id` FK; partial unique “one pending per (employee, report)”; PM-only approve; `_create_task_from_request` inserts a task row via the report service’s validators. |
| Benchmark live calc | `activity_master/service.py` | `get_daily_benchmark_ledger` halves target when report `day_status == half_day`; groups by (employee, date, sub_activity) with a *flat* target. `compute_benchmark(type, value, actual)`. Overdue/task queries unaffected by half-day. |
| Employee performance / pending export | `benchmarks/service.py` | Consumes the ledger rows — inherits period-correct targets automatically once the ledger is fixed. |
| Compliance | `report_compliance/service.py` | Date-level: worked attendance (present/half_day) vs submitted report existence. No fractions. |
| Reminder emails | `reminders/daily_report/service.py` | Date-level submitted-report existence. Unchanged by periods. |
| Weekly Activity Report | `work_reports/service.py::build_activity_rows/groups`, `reports_export/export.py` | One row per task + day-status-only rows for leave days; Excel template fixed. |
| Frontend form | `frontend/src/features/work-reports/components/work-report-form.tsx` (1701 lines) | Single-day form; `NO_APPROVAL_ACTIVITIES = {PROJECT MEETING, TRAINING, TRAINER}` bypass enforced client-side; second-activity → PM request flow; half-day target preview halves client-side. |
| Frontend schemas/types | `schemas.ts`, `types.ts` (openapi-generated) | zod form schema, `toCreateBody/toUpdateBody/toFormValues`. |
| Flags | `backend/app/core/config.py` (`TASK_CONTINUATION_ENABLED`), `frontend/src/lib/env.ts` (`features.*`) | Established mirror-flag pattern; `tests/conftest.py` pins flags off per test. |
| Migrations | `backend/alembic/versions/0001..0059` | String+CHECK used for newer enums (`activity_requests.status`); data backfills done in-migration with runtime resolution (0058 precedent). |

**Baseline noted:** ~11 pre-existing failures in `test_work_reports_service.py`/`test_work_reports_api.py` assert the removed approve/reject workflow (memory note, 2026-07-12). These are not regressions of this work.

---

## Design decisions locked in this plan

1. **Periods are always-on internally.** Once deployed, every create/update writes/refreshes period rows and links tasks — even with `REPORT_DAY_PARTS_ENABLED=false`. The flag gates only (a) accepting `report_mode="split_day"` / a `periods` payload and (b) the frontend selector. This keeps data uniform after backfill and makes flag-off behavior byte-identical for legacy clients. Read paths tolerate a missing period row (a report created by old code in the deploy gap) by treating the report as legacy full-day.
2. **New string columns use `VARCHAR + CHECK`, not new PG enums** (`report_mode`, `day_part`), following the `activity_requests.status` precedent — trivially reversible. `period_status` reuses the *existing* `day_status` PG enum type (`create_type=False`) so period statuses and header day statuses stay one taxonomy; nullable to mirror the header.
3. **Header derivation for split reports** (so every legacy reader — exports, compliance, reminders, ledger fallback — stays coherent without changes):
   - both periods working → `day_status` = first_half's status; `location` = first_half's location.
   - exactly one working → `day_status = half_day`; `location` = the working period's location.
   - both non-working → **rejected** (422: use Full Day mode for a fully non-working day).
4. **Benchmark fraction is row-level.** Effective target = base × fraction of the row's period (legacy row without a period: fraction = 0.5 iff header `day_status == half_day`, else 1.0 — bit-identical to today). Applied in `_apply_benchmarks` (frozen) and in `get_daily_benchmark_ledger` (live). Ledger target per (employee, date, sub_activity) becomes `base × min(1.0, Σ distinct-period fractions)` so the same activity in both halves reads target = base (aggregated), a single half reads base/2.
5. **`benchmark_value_snapshot` stays the effective target** (unchanged meaning); `benchmark_base_value_snapshot` and `benchmark_fraction_snapshot` are added beside it. Backfill derives base = effective / fraction for historical rows (×2 for `half_day` reports), leaving the effective value untouched.
6. **Activity requests** gain nullable `period_id`; approval inserts the row into that period (fallback: the report's first working period, then the full-day period). The “one pending request per (employee, report)” partial unique index is **kept as-is** (a per-period widening is a UX nicety, not a spec requirement — documented limitation).
7. **TASK_BASED / WorkItem behavior untouched:** `_task_based_dates`, WorkItem creation/continuation, and due-date freezing don't read fractions at all.
8. **Attendance module untouched.** Compliance adds derived per-day fractions + a warn-only mismatch flag (additive response fields).

### Deliberate parity decisions (explicitly NOT changed)
- Backend does not hard-cap “one normal activity per period”: today's backend accepts any task list (the allowance lives in the form + PM request flow, and approved requests are indistinguishable from normal rows on later resaves). The per-period allowance is enforced the same way, per period, in the UI. Server-side authorization (project membership, active project, RBAC scoping) remains authoritative as today.
- Weekly Activity Report Excel layout unchanged (rows are still per task row; leave-day placeholder rows unchanged; split-day reports appear with the derived header day status).
- Reminder emails / in-app compliance “report exists” stay date-level (one submitted header satisfies the day), per spec.

---

## File-by-file implementation plan

### Task 1: Migration `0060_work_report_periods` (additive, feature OFF)

**Files:**
- Create: `backend/alembic/versions/0060_work_report_periods.py`
- Test: `backend/tests/test_split_day_migration.py`

**Schema (upgrade):**
1. `daily_work_reports` + `report_mode VARCHAR(20) NOT NULL DEFAULT 'full_day'` + CHECK `IN ('full_day','split_day')`.
2. New table `work_report_periods`:
   - `id UUID PK`, `report_id UUID NOT NULL → daily_work_reports ON DELETE CASCADE`
   - `day_part VARCHAR(20) NOT NULL` + CHECK `IN ('full_day','first_half','second_half')`
   - `period_status day_status NULL` (existing PG enum, `create_type=False`)
   - `location work_location NULL` (existing PG enum)
   - `remarks TEXT NULL`
   - `work_fraction NUMERIC(3,2) NOT NULL` + CHECK `IN (0.5, 1.0)`
   - `is_legacy_half_day BOOLEAN NOT NULL DEFAULT false`
   - `created_at/updated_at timestamptz NOT NULL DEFAULT now()`
   - `UNIQUE (report_id, day_part)` (`work_report_periods_report_part_uq`), index on `report_id`.
3. `work_report_tasks` + `period_id UUID NULL → work_report_periods ON DELETE CASCADE`, index.
4. `work_report_tasks` + `benchmark_base_value_snapshot NUMERIC(10,2) NULL`, `benchmark_fraction_snapshot NUMERIC(3,2) NULL`.
5. `activity_requests` + `period_id UUID NULL → work_report_periods ON DELETE SET NULL`, index.

**Backfill (same migration, plain SQL over the bind — idempotent by construction):**
- For every report without a period row: insert one `full_day` period copying `day_status → period_status`, `location`, `remarks = NULL` (period remarks are new data; day remarks stay header-level), `work_fraction = 0.5` where `day_status = 'half_day'` else `1.0`, `is_legacy_half_day = (day_status = 'half_day')`. Use `INSERT … SELECT gen_random_uuid()…` if available, else Python-side uuid4 loop (0058 precedent).
- `UPDATE work_report_tasks SET period_id = p.id FROM work_report_periods p WHERE p.report_id = work_report_tasks.report_id AND work_report_tasks.period_id IS NULL`.
- Snapshot backfill for rows with `benchmark_value_snapshot IS NOT NULL AND benchmark_base_value_snapshot IS NULL`: `fraction = 0.5/1.0` from the report's `day_status`, `base = effective / fraction` (i.e. `× 2` on half-day), effective untouched.
- Activity requests with `report_id`: `period_id =` that report's period.

**Downgrade:** drop the five additions in reverse order (period data created after upgrade is lost on downgrade — documented; header/tasks/requests data all survive, nothing else references the new columns).

**Steps:**
- [ ] Write migration; `docker exec wms-backend-1 alembic upgrade head` against the dev DB via the test bootstrap (conftest runs it) — actually exercised by the test below.
- [ ] Write `test_split_day_migration.py`: seed pre-migration-shaped data is impossible post-hoc, so instead assert invariants on freshly-migrated DB + simulate legacy rows by inserting reports/tasks with `period_id=NULL` and re-running the backfill helpers if factored, plus an explicit `alembic downgrade 0059… / upgrade head` rehearsal test (pattern: existing `test_*_migration.py` files).
- [ ] Run: `docker exec wms-backend-1 pytest tests/test_split_day_migration.py -q` → PASS.

### Task 2: Backend flag + models + schemas

**Files:**
- Modify: `backend/app/core/config.py` — add `REPORT_DAY_PARTS_ENABLED: bool = False` (comment mirroring `TASK_CONTINUATION_ENABLED` style; frontend mirror named in comment).
- Modify: `backend/tests/conftest.py` — pin `REPORT_DAY_PARTS_ENABLED = False` in `_default_feature_flags`; add `day_parts_on` opt-in fixture.
- Modify: `backend/app/modules/work_reports/models.py`:
  - `class ReportMode(str, enum.Enum): full_day / split_day`
  - `class DayPart(str, enum.Enum): full_day / first_half / second_half`
  - `DAY_PART_FRACTIONS = {full_day: Decimal("1.0"), first_half: Decimal("0.5"), second_half: Decimal("0.5")}`
  - `DailyWorkReport.report_mode` (String(20) mapped, default 'full_day')
  - `class WorkReportPeriod(UUIDMixin, TimestampMixin, Base)` per the DDL above
  - `WorkReportTask.period_id`, `.benchmark_base_value_snapshot`, `.benchmark_fraction_snapshot`
- Modify: `backend/app/modules/activity_requests/models.py` — `period_id` column.
- Modify: `backend/app/modules/work_reports/schemas.py`:
  - `WorkReportPeriodIn`: `day_part`, `period_status: DayStatus`, `location: WorkLocation | None`, `remarks`, `tasks: list[WorkReportTaskIn]`. **No fraction field.**
  - `WorkReportPeriodOut`: id, day_part, period_status, location, remarks, `work_fraction: Decimal`, `is_legacy_half_day`, `tasks: list[WorkReportTaskOut]`.
  - `WorkReportCreate/Update` + optional `report_mode: ReportMode | None`, `periods: list[WorkReportPeriodIn] | None` (None = legacy payload).
  - `WorkReportTaskOut` + `period_id`, `day_part`, `benchmark_base_value_snapshot`, `benchmark_fraction_snapshot`.
  - `WorkReportOut` + `report_mode`, `periods: list[WorkReportPeriodOut] = []`.
- Modify: `backend/app/modules/activity_requests/schemas.py` — `period_id: uuid.UUID | None` on create/out.

### Task 3: Backend service — period invariants, legacy translation, fraction-aware benchmarks

**Files:**
- Modify: `backend/app/modules/work_reports/service.py`
- Modify: `backend/app/modules/activity_requests/service.py`
- Modify: `backend/app/modules/activity_master/service.py` (`get_daily_benchmark_ledger` only)

**Service-layer rules (`work_reports/service.py`):**
- `_normalize_periods(data) -> list[NormalizedPeriod]`: legacy payload (periods None) → one full_day period from header fields + `data.tasks`. Split payload allowed only when `settings.REPORT_DAY_PARTS_ENABLED` (else 422 `"Split-day reports are not enabled."`). Invariants (422 on violation): full_day mode ⇔ exactly one `full_day` period; split mode ⇔ exactly `{first_half, second_half}`; no mixing; duplicate day_part impossible; non-working period (`period_status ∈ NO_ACTIVITY_DAY_STATUSES`) must carry zero tasks (tasks sent anyway are dropped, matching today's leniency) and no location; working period requires location per current form rules (validated client-side today — server keeps parity, not stricter); both-halves-non-working → 422; `half_day` not allowed as a *period* status of a split report (422).
- Header derivation per Design decision 3; `report_mode` stamped on the header.
- `create_work_report` / `update_work_report`: write period rows (delete+recreate alongside the existing task delete+recreate; preserves the existing WorkItem reconcile logic by running it unchanged), link every task row to its period. Working-period “≥1 activity” enforced at **submit** (as today for the day level): `submit_work_report` checks per period.
- `_apply_benchmarks`: per row — resolve fraction from the row's period (`period.work_fraction`) else legacy header rule; freeze `benchmark_base_value_snapshot = sub.benchmark_value`, `benchmark_fraction_snapshot = fraction`, `benchmark_value_snapshot = base × fraction`; deficit/productivity computed against the effective value exactly as before (`compute_benchmark` unchanged). NUMERIC-family types only, as today.
- `_attach_tasks` / `_decorate`: batch-load periods, expose `report.periods` (each with its trimmed task list mirroring the Lead row-trim: a Lead-scoped report's periods expose only led rows; periods left empty after trimming are still listed with metadata), stamp `day_part`+snapshots onto task rows.
- Read tolerance: report without period rows → synthesize (not persist) one full_day period from the header for the response.
- `get_daily_benchmark_ledger` (`activity_master/service.py`): outer-join `WorkReportPeriod` on `WorkReportTask.period_id`; per (employee, date, sub_activity) bucket track distinct `(period_id or 'legacy', fraction)`; `target = base × min(1, Σ fractions)`; legacy fraction = 0.5 iff `day_status == half_day` else 1.0 (today's behavior preserved bit-for-bit for legacy rows).
- `activity_requests`: `create_request` stores `period_id` (validated: belongs to that report, is a working period); `approve_request → _create_task_from_request` writes the task row with the request's `period_id` (fallback: first working period of the report, else the report's only period); `_attach_names` surfaces `day_part` for the PM view.

### Task 4: Compliance fractions (warn-only)

**Files:**
- Modify: `backend/app/modules/report_compliance/service.py`, `schemas.py`, `router.py` (schema only if response model is explicit)

Additive response fields on `employee_compliance`:
- `reported_work_fraction_today: float | None` — Σ working-period fractions of today's submitted report (None when no submitted report).
- `attendance_work_fraction_today: float | None` — 1.0 for `present`, 0.5 for `half_day`, None otherwise/no record.
- `fraction_mismatch_today: bool` — both present and unequal → warn (UI copy later; no blocking, `pending_*` untouched).

### Task 5: Backend tests (split-day matrix)

**Files:**
- Create: `backend/tests/test_work_report_periods.py`
- Modify: `backend/tests/test_activity_requests.py` (period routing cases)
- Create: `backend/tests/test_split_day_migration.py` (Task 1)
- Modify: `backend/tests/test_benchmark_engine.py` or new `test_split_day_benchmarks.py` for ledger fraction cases

Matrix (each a test):
- Legacy payload (no `periods`) → full_day report + one period + linked tasks; response shape unchanged fields intact (regression: exact-count tests keep passing).
- Flag OFF + split payload → 422; flag ON → accepted.
- Full-day work; full-day leave (leave-type day statuses still task-free).
- First-half leave + second-half work, and the reverse: header `day_status == half_day`, working period fraction 0.5, effective = base/2 frozen at submit (base 120 → 60), base+fraction snapshots frozen; count read from the row's relevant field; deficit/productivity vs 60.
- Two working halves, different activities: each frozen at base × 0.5.
- Same activity in both halves: two rows kept; ledger target = base (not 2×base), actual summed.
- Non-working period with tasks → tasks dropped/422 per rule; working period without tasks → submit 422.
- Fractions not client-suppliable (schema has no field; extra JSON keys ignored — assert a spoofed `work_fraction` in the payload has no effect).
- TASK_BASED row in a half period: due_date unchanged (= report_date + period_days − 1), no fraction applied.
- Exempt activities (Project Meeting/Training/Trainer): unchanged server behavior (no server gate — parity test that a two-task split payload saves).
- Activity request with `period_id` → approved row lands in that period; legacy request (no period) → falls back to working period.
- Activity Lead partial visibility on a split report: led rows only, periods metadata intact; direct URL access unchanged (403 paths).
- Head grant-edit / self-edit flows still work on split reports (status transitions untouched).
- Compliance: fractions + mismatch warn for present-vs-half-report and half_day-vs-full-report.
- Migration upgrade/downgrade rehearsal.
- Backfill: pre-existing `half_day` report → legacy full_day period, fraction 0.5, `is_legacy_half_day`, effective snapshot preserved, base = 2×effective.

Run: `docker exec wms-backend-1 pytest tests/ -q` (full suite; compare against the ~11-known-failure baseline).

### Task 6: OpenAPI types regeneration

- Fetch `http://localhost:8100/api/v1/openapi.json` → `frontend/openapi.json` (2-space pretty) → `npx --no-install openapi-typescript openapi.json -o src/types/openapi.ts` (host has node_modules).

### Task 7: Frontend flag + period components (extract, no behavior change first)

**Files:**
- Modify: `frontend/src/lib/env.ts` — `features.reportDayParts = process.env.NEXT_PUBLIC_REPORT_DAY_PARTS_ENABLED === "true"`.
- Create: `frontend/src/features/work-reports/components/period-activity-editor.tsx` — the per-task-row editor extracted verbatim from `work-report-form.tsx` (project/plant/activity/sub-activity/counts/task-benchmark card/continuation UI), parameterized by field-array path prefix + a `fractionLabel`/target-scaling input so a half period previews `target/2`.
- Create: `frontend/src/features/work-reports/components/report-period-card.tsx` — status selector (period statuses), location (working only), remarks, activity editor, benchmark preview, approval-state slot; confirm dialog when switching Working → Leave/Off with activities present (reuses `alert-dialog`).
- Modify: `work-report-form.tsx` — Full-Day path renders the same extracted components (single hidden full_day period), so Full Day / First Half / Second Half share one implementation. No visible change with the flag off.

### Task 8: Frontend split-day experience (flag ON)

**Files:**
- Modify: `frontend/src/features/work-reports/schemas.ts` — form schema gains `report_mode` + `periods[]` (each: day_part, period_status, location, remarks, tasks[]); `toCreateBody/toUpdateBody` emit the periods payload when split, the legacy payload when full-day; `toFormValues` maps `report.periods`.
- Modify: `work-report-form.tsx` — Day Format selector (`Full Day | Split Day`, flag-gated); split renders two `ReportPeriodCard`s side-by-side on `lg:` (`grid lg:grid-cols-2`), stacked on mobile; “Copy first-half activity to second half”; daily summary strip (working fraction, leave fraction, activities, effective target Σ, actual Σ); submission review dialog before submit.
- Modify: `work-report-detail.tsx` — split reports group tasks under First/Second-Half headings with period status/location/remarks + fraction; full-day rendering unchanged; legacy half-day marker surfaced (“Half Day (legacy)”).
- Modify: `work-reports-table.tsx` / list — mode badge (“Split”) when `report_mode === "split_day"`.
- Modify: `frontend/src/features/activity-requests/*` — request carries `period_id`; PM view shows “First Half / Second Half” tag.
- Modify: `frontend/src/features/report-compliance/*` — surface the warn-only mismatch line when fields present.

Verify: `docker exec wms-frontend-1 sh -c "cd /app && npm run typecheck"`, existing vitest files, and a manual run-through of the form with the flag on/off.

### Task 9: Docs & rollout notes

- Update `docs/DAILY_WORK_REPORTS_SPEC.md` addendum section pointing at this plan; `.env.example` entries for both flags.

---

## Rollout (delivery process mapping)

1. Plan (this document).
2. Migration 0060 merges + deploys with both flags OFF — behavior unchanged, data backfilled.
3. Backend compat + tests (flags still OFF in prod).
4. Frontend behind `NEXT_PUBLIC_REPORT_DAY_PARTS_ENABLED`.
5. Production-clone rehearsal: `alembic upgrade head` on a clone; row-count + spot-check queries (half_day report snapshots, ledger parity before/after) — operator step.
6. Pilot: enable both flags for a staging/pilot environment.
7. Production enable.
8. Attendance period redesign — separate future plan (out of scope here).

## Assumptions & remaining risks

- **Assumption:** period remarks are new data; historical reports keep remarks at the header (not copied into the backfilled period).
- **Assumption:** a split report with both halves non-working is invalid (use full-day leave).
- **Assumption:** `half_day` stays selectable as a *header* day status for full-day-mode reports (legacy behavior) even with the flag on; the UI may later steer users to Split Day, but nothing breaks.
- **Risk:** deploy gap between migration and old code writing reports without periods — mitigated by read-path synthesis + write-path repair; the ledger/`_apply_benchmarks` legacy fallback keeps math correct for such rows.
- **Risk:** the 1701-line form refactor is the highest-touch change; mitigated by extracting components verbatim first (Task 7, no behavior change, typecheck + flag-off parity) before adding split UI (Task 8).
- **Limitation (documented):** one pending activity request per report (not per period) — unchanged DB constraint.
