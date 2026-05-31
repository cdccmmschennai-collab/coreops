-- =============================================================
-- WorkTrack — Daily reports + entries
-- 04_daily_reports.sql
--
-- A daily report has ONE header per (employee, date) and N entries (one per
-- project+activity combination worked that day). Counts (Tags / Docs / BOM /
-- Spares / Tasks) live on the entry, not the header — different projects can
-- contribute different counts on the same day.
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- daily_reports --------------------------------------------------
CREATE TABLE daily_reports (
  id               uuid                       PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id      uuid                       NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
  report_date      date                       NOT NULL,

  -- Day metadata (drives validation: leave/holiday days do not require entries)
  day_status       worktrack.day_status       NOT NULL DEFAULT 'working',
  work_location    text                       NULL,    -- 'office_hq', 'wfh', 'client_site' etc — free-form picklist
  shift_id         uuid                       NULL REFERENCES shifts(id) ON DELETE SET NULL,

  -- Aggregates — denormalized for the dashboard hot path. Maintained by the
  -- application (or by a trigger summing daily_report_entries; see notes).
  total_hours          numeric(6, 2)          NOT NULL DEFAULT 0,
  total_tasks_done     integer                NOT NULL DEFAULT 0,
  total_tasks_open     integer                NOT NULL DEFAULT 0,

  -- Workflow
  status           worktrack.report_status    NOT NULL DEFAULT 'draft',
  submitted_at     timestamptz                NULL,
  reviewed_by      uuid                       NULL REFERENCES employees(id) ON DELETE SET NULL,
  reviewed_at      timestamptz                NULL,
  review_note      text                       NULL,

  -- Edit window — auto-locked at +24h after submission (see scheduled job).
  locked_at        timestamptz                NULL,

  -- Free-form fields
  remarks          text                       NULL,
  queries          text                       NULL,    -- @mentions extracted into mentions table

  -- Optimistic concurrency: bump on every save.
  version          integer                    NOT NULL DEFAULT 1,

  created_at       timestamptz                NOT NULL DEFAULT now(),
  updated_at       timestamptz                NOT NULL DEFAULT now(),
  created_by       uuid                       NULL,
  updated_by       uuid                       NULL,
  deleted_at       timestamptz                NULL,

  CONSTRAINT daily_reports_hours_nonneg CHECK (total_hours >= 0),
  CONSTRAINT daily_reports_reviewed_consistency CHECK (
    (reviewed_at IS NULL AND reviewed_by IS NULL) OR
    (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)
  )
);

-- One report per employee per date. Soft-deleted rows do not block re-submission.
CREATE UNIQUE INDEX daily_reports_emp_date_uq
  ON daily_reports (employee_id, report_date) WHERE deleted_at IS NULL;

CREATE INDEX daily_reports_emp_recent_idx
  ON daily_reports (employee_id, report_date DESC) WHERE deleted_at IS NULL;

CREATE INDEX daily_reports_status_idx
  ON daily_reports (status, report_date DESC) WHERE deleted_at IS NULL;

-- Manager review queue: pending reviewer-side reports for the reviewing manager.
CREATE INDEX daily_reports_review_queue_idx
  ON daily_reports (reviewed_by, status, submitted_at DESC)
  WHERE deleted_at IS NULL AND status IN ('submitted', 'in_review');

CREATE TRIGGER daily_reports_audit
  BEFORE INSERT OR UPDATE ON daily_reports
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- daily_report_entries -------------------------------------------
-- The counts grid: Tags / Docs / BOM / Spares / Tasks_done / Tasks_open.
-- One row per (project, activity_type) within a report.
CREATE TABLE daily_report_entries (
  id                 uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  daily_report_id    uuid          NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
  project_id         uuid          NOT NULL REFERENCES projects(id)       ON DELETE RESTRICT,
  activity_type_id   uuid          NOT NULL REFERENCES activity_types(id) ON DELETE RESTRICT,
  hours              numeric(5, 2) NOT NULL DEFAULT 0,

  -- Domain counts (per WorkTrack spec)
  tags_count         integer       NOT NULL DEFAULT 0,
  docs_count         integer       NOT NULL DEFAULT 0,
  bom_count          integer       NOT NULL DEFAULT 0,
  spares_count       integer       NOT NULL DEFAULT 0,
  tasks_done_count   integer       NOT NULL DEFAULT 0,
  tasks_open_count   integer       NOT NULL DEFAULT 0,

  note               text          NULL,
  position           integer       NOT NULL DEFAULT 0,    -- ordering within report

  created_at         timestamptz   NOT NULL DEFAULT now(),
  updated_at         timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT dre_hours_nonneg  CHECK (hours >= 0 AND hours <= 24),
  CONSTRAINT dre_counts_nonneg CHECK (
    tags_count >= 0 AND docs_count >= 0 AND bom_count >= 0 AND
    spares_count >= 0 AND tasks_done_count >= 0 AND tasks_open_count >= 0
  )
);

CREATE INDEX dre_report_idx   ON daily_report_entries (daily_report_id, position);
CREATE INDEX dre_project_idx  ON daily_report_entries (project_id);
CREATE INDEX dre_activity_idx ON daily_report_entries (activity_type_id);

CREATE TRIGGER dre_touch BEFORE UPDATE ON daily_report_entries
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- daily_report_history -------------------------------------------
-- Versioned snapshots, captured every time a report is submitted or edited
-- after submission. Lets HR/audit reconstruct the exact body that was filed
-- at any past timestamp, separate from the catch-all audit_logs.
CREATE TABLE daily_report_history (
  id               uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  daily_report_id  uuid          NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
  version          integer       NOT NULL,
  change_type      text          NOT NULL,   -- 'submit' | 'edit' | 'review' | 'reject'
  changed_by       uuid          NULL REFERENCES employees(id) ON DELETE SET NULL,
  snapshot         jsonb         NOT NULL,
  created_at       timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX drh_report_idx ON daily_report_history (daily_report_id, version DESC);


-- ---------- daily_report_mentions ------------------------------------------
-- Extracted from remarks/queries to drive @mention notifications cleanly.
CREATE TABLE daily_report_mentions (
  id               uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  daily_report_id  uuid          NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
  mentioned_employee_id uuid     NOT NULL REFERENCES employees(id)     ON DELETE CASCADE,
  source           text          NOT NULL,   -- 'remarks' | 'queries'
  created_at       timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX drm_report_idx   ON daily_report_mentions (daily_report_id);
CREATE INDEX drm_employee_idx ON daily_report_mentions (mentioned_employee_id, created_at DESC);
