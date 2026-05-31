-- =============================================================
-- WorkTrack — Employees, Departments, Locations, Shifts
-- 02_employees.sql
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- locations ------------------------------------------------------
CREATE TABLE locations (
  id           uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  code         text          NOT NULL,
  name         text          NOT NULL,
  timezone     text          NOT NULL DEFAULT 'UTC',
  address_line text          NULL,
  city         text          NULL,
  country_code char(2)       NULL,
  is_active    boolean       NOT NULL DEFAULT true,
  created_at   timestamptz   NOT NULL DEFAULT now(),
  updated_at   timestamptz   NOT NULL DEFAULT now(),
  deleted_at   timestamptz   NULL
);
CREATE UNIQUE INDEX locations_code_uq ON locations (code) WHERE deleted_at IS NULL;
CREATE TRIGGER locations_touch BEFORE UPDATE ON locations
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- departments ----------------------------------------------------
-- Self-referencing tree. Head is materialized as an FK for fast lookups.
CREATE TABLE departments (
  id                uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  code              text          NOT NULL,
  name              text          NOT NULL,
  parent_id         uuid          NULL REFERENCES departments(id) ON DELETE RESTRICT,
  head_employee_id  uuid          NULL,    -- FK set after employees table is created
  is_active         boolean       NOT NULL DEFAULT true,

  created_at        timestamptz   NOT NULL DEFAULT now(),
  updated_at        timestamptz   NOT NULL DEFAULT now(),
  created_by        uuid          NULL,
  updated_by        uuid          NULL,
  deleted_at        timestamptz   NULL,

  CONSTRAINT departments_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE UNIQUE INDEX departments_code_uq   ON departments (code)      WHERE deleted_at IS NULL;
CREATE INDEX        departments_parent_ix ON departments (parent_id) WHERE deleted_at IS NULL;

CREATE TRIGGER departments_audit
  BEFORE INSERT OR UPDATE ON departments
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- shifts ---------------------------------------------------------
-- Working_days is a 7-bit mask: bit 0 = Monday … bit 6 = Sunday.
-- Times are stored as time (local), interpreted in the shift's timezone.
CREATE TABLE shifts (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  code            text          NOT NULL,
  name            text          NOT NULL,
  start_time      time          NOT NULL,
  end_time        time          NOT NULL,
  break_minutes   integer       NOT NULL DEFAULT 60,
  crosses_midnight boolean      NOT NULL DEFAULT false,
  working_days_mask smallint    NOT NULL DEFAULT 31,   -- 31 = Mon-Fri
  timezone        text          NOT NULL DEFAULT 'UTC',
  is_active       boolean       NOT NULL DEFAULT true,

  created_at      timestamptz   NOT NULL DEFAULT now(),
  updated_at      timestamptz   NOT NULL DEFAULT now(),
  deleted_at      timestamptz   NULL,

  CONSTRAINT shifts_break_nonneg CHECK (break_minutes >= 0),
  CONSTRAINT shifts_mask_range   CHECK (working_days_mask BETWEEN 0 AND 127)
);
CREATE UNIQUE INDEX shifts_code_uq ON shifts (code) WHERE deleted_at IS NULL;
CREATE TRIGGER shifts_touch BEFORE UPDATE ON shifts
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- employees ------------------------------------------------------
-- user_id is nullable to support pre-onboarding placeholders (created before
-- an SSO identity exists). employee_code is the human-facing ID printed on
-- ID cards and used in HR exports.
CREATE TABLE employees (
  id                  uuid                          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid                          NULL REFERENCES auth_users(id) ON DELETE SET NULL,

  employee_code       text                          NOT NULL,    -- e.g. 'EMP-00184'
  first_name          text                          NOT NULL,
  last_name           text                          NOT NULL,
  display_name        text                          GENERATED ALWAYS AS (trim(first_name || ' ' || last_name)) STORED,
  work_email          citext                        NULL,
  personal_email      citext                        NULL,
  phone               text                          NULL,
  photo_url           text                          NULL,

  department_id       uuid                          NULL REFERENCES departments(id) ON DELETE SET NULL,
  designation         text                          NULL,        -- 'Senior Engineer'
  grade               text                          NULL,        -- 'L5'
  employment_type     worktrack.employment_type     NOT NULL DEFAULT 'full_time',
  employment_status   worktrack.employment_status   NOT NULL DEFAULT 'active',

  -- Manager hierarchy. RESTRICT keeps us from accidentally orphaning teams
  -- when a manager is deleted — the app must reassign first.
  manager_id          uuid                          NULL REFERENCES employees(id) ON DELETE RESTRICT,

  location_id         uuid                          NULL REFERENCES locations(id) ON DELETE SET NULL,
  default_shift_id    uuid                          NULL REFERENCES shifts(id)    ON DELETE SET NULL,
  timezone            text                          NULL,        -- override location TZ

  date_of_joining     date                          NULL,
  date_of_confirmation date                         NULL,
  date_of_exit        date                          NULL,

  created_at          timestamptz                   NOT NULL DEFAULT now(),
  updated_at          timestamptz                   NOT NULL DEFAULT now(),
  created_by          uuid                          NULL,
  updated_by          uuid                          NULL,
  deleted_at          timestamptz                   NULL,

  CONSTRAINT employees_no_self_manager CHECK (manager_id IS NULL OR manager_id <> id),
  CONSTRAINT employees_exit_after_join CHECK (date_of_exit IS NULL OR date_of_joining IS NULL OR date_of_exit >= date_of_joining)
);

CREATE UNIQUE INDEX employees_code_uq
  ON employees (employee_code) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX employees_work_email_uq
  ON employees (work_email) WHERE work_email IS NOT NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX employees_user_id_uq
  ON employees (user_id) WHERE user_id IS NOT NULL AND deleted_at IS NULL;

-- Hot lookup indexes
CREATE INDEX employees_department_idx ON employees (department_id)        WHERE deleted_at IS NULL;
CREATE INDEX employees_manager_idx    ON employees (manager_id)           WHERE deleted_at IS NULL;
CREATE INDEX employees_status_idx     ON employees (employment_status)    WHERE deleted_at IS NULL;
CREATE INDEX employees_location_idx   ON employees (location_id)          WHERE deleted_at IS NULL;

-- Display-name trigram-style ilike search (use pg_trgm in production)
CREATE INDEX employees_display_name_idx ON employees ((lower(display_name))) WHERE deleted_at IS NULL;

CREATE TRIGGER employees_audit
  BEFORE INSERT OR UPDATE ON employees
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- Now that employees exists, wire the departments.head_employee_id FK.
ALTER TABLE departments
  ADD CONSTRAINT departments_head_employee_fk
  FOREIGN KEY (head_employee_id) REFERENCES employees(id) ON DELETE SET NULL;


-- ---------- employment_history --------------------------------------------
-- An audit-light record of role/department/manager changes. Updated by the
-- application whenever any of the tracked fields on `employees` changes; this
-- is for HR-facing history, not for the full audit log.
CREATE TABLE employment_history (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id     uuid          NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  effective_date  date          NOT NULL,
  end_date        date          NULL,
  department_id   uuid          NULL REFERENCES departments(id),
  manager_id      uuid          NULL REFERENCES employees(id),
  designation     text          NULL,
  grade           text          NULL,
  reason          text          NULL,    -- 'promotion' | 'transfer' | 'rehire'
  created_at      timestamptz   NOT NULL DEFAULT now(),
  created_by      uuid          NULL
);
CREATE INDEX employment_history_emp_idx ON employment_history (employee_id, effective_date DESC);
