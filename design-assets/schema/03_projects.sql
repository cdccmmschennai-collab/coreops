-- =============================================================
-- WorkTrack — Projects, activity types, project members
-- 03_projects.sql
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- activity_types -------------------------------------------------
-- Picklist for daily-report entries. Admin-editable.
CREATE TABLE activity_types (
  id          uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text          NOT NULL,    -- 'dev', 'code_review', 'meeting'
  name        text          NOT NULL,    -- 'Development'
  description text          NULL,
  is_billable boolean       NOT NULL DEFAULT true,
  display_order integer     NOT NULL DEFAULT 100,
  is_active   boolean       NOT NULL DEFAULT true,

  created_at  timestamptz   NOT NULL DEFAULT now(),
  updated_at  timestamptz   NOT NULL DEFAULT now(),
  deleted_at  timestamptz   NULL
);
CREATE UNIQUE INDEX activity_types_code_uq ON activity_types (code) WHERE deleted_at IS NULL;
CREATE TRIGGER activity_types_touch BEFORE UPDATE ON activity_types
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- projects -------------------------------------------------------
CREATE TABLE projects (
  id                uuid                       PRIMARY KEY DEFAULT gen_random_uuid(),
  code              text                       NOT NULL,    -- 'WT-WEB-14'
  name              text                       NOT NULL,
  description       text                       NULL,
  status            worktrack.project_status   NOT NULL DEFAULT 'active',
  color             text                       NULL,        -- hex for charts
  department_id     uuid                       NULL REFERENCES departments(id) ON DELETE SET NULL,
  owner_employee_id uuid                       NULL REFERENCES employees(id)   ON DELETE SET NULL,

  start_date        date                       NULL,
  end_date          date                       NULL,
  allocated_hours   numeric(10, 2)             NULL,        -- budget in hours
  is_billable       boolean                    NOT NULL DEFAULT true,

  metadata          jsonb                      NOT NULL DEFAULT '{}'::jsonb,

  created_at        timestamptz                NOT NULL DEFAULT now(),
  updated_at        timestamptz                NOT NULL DEFAULT now(),
  created_by        uuid                       NULL,
  updated_by        uuid                       NULL,
  deleted_at        timestamptz                NULL,

  CONSTRAINT projects_dates CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE UNIQUE INDEX projects_code_uq        ON projects (code)              WHERE deleted_at IS NULL;
CREATE INDEX        projects_status_idx     ON projects (status)            WHERE deleted_at IS NULL;
CREATE INDEX        projects_department_idx ON projects (department_id)    WHERE deleted_at IS NULL;
CREATE INDEX        projects_owner_idx      ON projects (owner_employee_id) WHERE deleted_at IS NULL;
CREATE INDEX        projects_active_dates_idx ON projects (start_date, end_date)
  WHERE deleted_at IS NULL AND status IN ('active', 'at_risk');
CREATE INDEX        projects_metadata_gin   ON projects USING gin (metadata);

CREATE TRIGGER projects_audit
  BEFORE INSERT OR UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- project_members ------------------------------------------------
-- Many-to-many: an employee can join the same project multiple times over
-- their career (separate rows with left_at populated for old stints).
CREATE TABLE project_members (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid          NOT NULL REFERENCES projects(id)  ON DELETE CASCADE,
  employee_id     uuid          NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
  role_in_project text          NULL,        -- 'lead', 'reviewer', 'contributor'
  allocated_pct   smallint      NOT NULL DEFAULT 100,    -- expected utilization
  joined_at       timestamptz   NOT NULL DEFAULT now(),
  left_at         timestamptz   NULL,
  created_by      uuid          NULL,

  CONSTRAINT project_members_pct CHECK (allocated_pct BETWEEN 0 AND 100),
  CONSTRAINT project_members_left_after_join CHECK (left_at IS NULL OR left_at >= joined_at)
);

-- A single open membership per (project, employee).
CREATE UNIQUE INDEX project_members_open_uq
  ON project_members (project_id, employee_id) WHERE left_at IS NULL;

CREATE INDEX project_members_employee_idx ON project_members (employee_id) WHERE left_at IS NULL;
CREATE INDEX project_members_project_idx  ON project_members (project_id)  WHERE left_at IS NULL;
