-- =============================================================
-- WorkTrack — Leave management
-- 06_leave.sql
--
-- Conceptual model:
--   leave_types          — admin-defined catalog (CL, SL, EL, CO, BL, PL …)
--   leave_balances       — per (employee, type, period) running balance
--   leave_requests       — application from an employee
--   leave_request_days   — expanded per-day rows (incl. half-day fractions)
--   leave_accruals       — append-only credit events feeding the balance
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- leave_types ----------------------------------------------------
-- Admin-extensible. Quota is the annual entitlement; accrual_method tells the
-- scheduler when to mint leave_accruals rows.
CREATE TABLE leave_types (
  id                          uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  code                        text          NOT NULL,    -- 'CL', 'SL', 'EL', 'CO', 'BL', 'PL'
  name                        text          NOT NULL,
  description                 text          NULL,
  is_paid                     boolean       NOT NULL DEFAULT true,
  annual_quota                numeric(5, 2) NOT NULL DEFAULT 0,
  accrual_method              text          NOT NULL DEFAULT 'annual_grant',  -- 'annual_grant' | 'monthly_accrual' | 'none'
  accrual_rate_per_month      numeric(5, 2) NULL,
  max_carry_forward           numeric(5, 2) NOT NULL DEFAULT 0,
  max_balance                 numeric(5, 2) NULL,        -- cap if not null
  requires_proof_after_days   integer       NULL,        -- doctor's note after N days
  allows_half_day             boolean       NOT NULL DEFAULT true,
  min_notice_days             integer       NOT NULL DEFAULT 0,
  is_active                   boolean       NOT NULL DEFAULT true,

  created_at                  timestamptz   NOT NULL DEFAULT now(),
  updated_at                  timestamptz   NOT NULL DEFAULT now(),
  deleted_at                  timestamptz   NULL
);
CREATE UNIQUE INDEX leave_types_code_uq ON leave_types (code) WHERE deleted_at IS NULL;
CREATE TRIGGER leave_types_touch BEFORE UPDATE ON leave_types
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- leave_balances -------------------------------------------------
-- One row per (employee, type, period_year). Maintained incrementally by the
-- application; never decremented below zero by SQL — the app validates first.
-- current_balance = opening + accrued + carried_forward - used - encashed.
CREATE TABLE leave_balances (
  id              uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id     uuid           NOT NULL REFERENCES employees(id)   ON DELETE CASCADE,
  leave_type_id   uuid           NOT NULL REFERENCES leave_types(id) ON DELETE RESTRICT,
  period_year     smallint       NOT NULL,    -- 2026 etc

  opening_balance     numeric(6, 2) NOT NULL DEFAULT 0,
  accrued             numeric(6, 2) NOT NULL DEFAULT 0,
  carried_forward     numeric(6, 2) NOT NULL DEFAULT 0,
  used                numeric(6, 2) NOT NULL DEFAULT 0,
  encashed            numeric(6, 2) NOT NULL DEFAULT 0,
  adjustments         numeric(6, 2) NOT NULL DEFAULT 0,    -- manual HR tweaks

  -- Computed column for the dashboard hot path.
  current_balance     numeric(6, 2) GENERATED ALWAYS AS
    (opening_balance + accrued + carried_forward + adjustments - used - encashed) STORED,

  updated_at      timestamptz    NOT NULL DEFAULT now(),
  updated_by      uuid           NULL,

  CONSTRAINT lb_year_range CHECK (period_year BETWEEN 2000 AND 2200),
  CONSTRAINT lb_nonneg     CHECK (
    opening_balance >= 0 AND accrued >= 0 AND used >= 0 AND
    encashed >= 0 AND carried_forward >= 0
  )
);

CREATE UNIQUE INDEX leave_balances_uq
  ON leave_balances (employee_id, leave_type_id, period_year);
CREATE INDEX leave_balances_emp_idx ON leave_balances (employee_id, period_year DESC);

CREATE TRIGGER leave_balances_touch BEFORE UPDATE ON leave_balances
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- leave_accruals -------------------------------------------------
-- Append-only event log for balance credits. Replayable. The leave_balances
-- table is a materialized read of all accruals + requests; if balances ever
-- look wrong, rebuild them from this table + leave_requests.
CREATE TABLE leave_accruals (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id     uuid          NOT NULL REFERENCES employees(id)   ON DELETE CASCADE,
  leave_type_id   uuid          NOT NULL REFERENCES leave_types(id) ON DELETE RESTRICT,
  effective_date  date          NOT NULL,
  amount          numeric(6, 2) NOT NULL,    -- positive=credit, negative=debit
  reason          text          NOT NULL,    -- 'monthly_accrual' | 'annual_grant' | 'manual_adjustment' | 'carry_forward'
  notes           text          NULL,
  created_by      uuid          NULL,
  created_at      timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX leave_accruals_emp_type_idx ON leave_accruals (employee_id, leave_type_id, effective_date DESC);
CREATE INDEX leave_accruals_date_idx     ON leave_accruals (effective_date);


-- ---------- leave_requests -------------------------------------------------
CREATE TABLE leave_requests (
  id                  uuid                            PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id         uuid                            NOT NULL REFERENCES employees(id)   ON DELETE RESTRICT,
  leave_type_id       uuid                            NOT NULL REFERENCES leave_types(id) ON DELETE RESTRICT,

  start_date          date                            NOT NULL,
  end_date            date                            NOT NULL,
  days_count          numeric(5, 2)                   NOT NULL,    -- sum of fractions in leave_request_days

  is_half_day         boolean                         NOT NULL DEFAULT false,
  half_day_segment    text                            NULL,        -- 'first' | 'second' — only when is_half_day

  reason              text                            NOT NULL,
  proof_url           text                            NULL,        -- doctor's note, etc.

  status              worktrack.leave_request_status  NOT NULL DEFAULT 'pending',
  applied_at          timestamptz                     NOT NULL DEFAULT now(),

  decided_by          uuid                            NULL REFERENCES employees(id) ON DELETE SET NULL,
  decided_at          timestamptz                     NULL,
  decision_note       text                            NULL,

  cancelled_at        timestamptz                     NULL,
  cancellation_reason text                            NULL,

  created_at          timestamptz                     NOT NULL DEFAULT now(),
  updated_at          timestamptz                     NOT NULL DEFAULT now(),
  created_by          uuid                            NULL,
  updated_by          uuid                            NULL,
  deleted_at          timestamptz                     NULL,

  CONSTRAINT lr_dates       CHECK (end_date >= start_date),
  CONSTRAINT lr_days_pos    CHECK (days_count > 0),
  CONSTRAINT lr_half_segment CHECK (
    (is_half_day = false AND half_day_segment IS NULL) OR
    (is_half_day = true  AND half_day_segment IN ('first', 'second'))
  )
);

CREATE INDEX leave_requests_emp_idx          ON leave_requests (employee_id, applied_at DESC);
CREATE INDEX leave_requests_pending_idx      ON leave_requests (applied_at DESC) WHERE status = 'pending' AND deleted_at IS NULL;
CREATE INDEX leave_requests_decision_idx     ON leave_requests (decided_by, decided_at DESC) WHERE decided_by IS NOT NULL;
CREATE INDEX leave_requests_overlap_idx      ON leave_requests (employee_id, start_date, end_date) WHERE deleted_at IS NULL AND status IN ('pending', 'approved');

CREATE TRIGGER leave_requests_audit
  BEFORE INSERT OR UPDATE ON leave_requests
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- leave_request_days ---------------------------------------------
-- Per-day expansion of a request. Lets us mark some days half / full, exclude
-- holidays cleanly, and join into attendance_records day-by-day.
CREATE TABLE leave_request_days (
  id                uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  leave_request_id  uuid          NOT NULL REFERENCES leave_requests(id) ON DELETE CASCADE,
  leave_date        date          NOT NULL,
  day_fraction      numeric(3, 2) NOT NULL DEFAULT 1.0,    -- 0.50 or 1.00
  is_holiday        boolean       NOT NULL DEFAULT false,
  is_weekend        boolean       NOT NULL DEFAULT false,
  created_at        timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT lrd_fraction CHECK (day_fraction IN (0.5, 1.0))
);
CREATE UNIQUE INDEX leave_request_days_uq ON leave_request_days (leave_request_id, leave_date);
CREATE INDEX leave_request_days_date_idx  ON leave_request_days (leave_date);


-- Wire attendance_records.leave_request_id (from 05) now that the table exists
ALTER TABLE attendance_records
  ADD CONSTRAINT attendance_leave_request_fk
  FOREIGN KEY (leave_request_id) REFERENCES leave_requests(id) ON DELETE SET NULL;
