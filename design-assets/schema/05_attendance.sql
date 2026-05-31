-- =============================================================
-- WorkTrack — Attendance: records, punches, corrections, holidays
-- 05_attendance.sql
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- attendance_records ---------------------------------------------
-- ONE row per (employee, attendance_date). The materialized daily summary —
-- it's the source of truth for the attendance calendar and the leave-balance
-- consumer. Authored by a scheduled job that aggregates punches + leave +
-- holidays at the close of each day, with manual edits via corrections.
CREATE TABLE attendance_records (
  id                 uuid                          PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id        uuid                          NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
  attendance_date    date                          NOT NULL,
  status             worktrack.attendance_status   NOT NULL,
  shift_id           uuid                          NULL REFERENCES shifts(id) ON DELETE SET NULL,

  check_in_at        timestamptz                   NULL,
  check_out_at       timestamptz                   NULL,
  total_minutes      integer                       NOT NULL DEFAULT 0,
  break_minutes      integer                       NOT NULL DEFAULT 0,

  -- Provenance flags
  is_corrected       boolean                       NOT NULL DEFAULT false,
  source             worktrack.punch_source        NOT NULL DEFAULT 'system',

  -- Optional link to the leave_request that drove status='leave'
  leave_request_id   uuid                          NULL,    -- FK added in 06_leave.sql
  -- Optional link to the holiday that drove status='holiday'
  holiday_id         uuid                          NULL,    -- FK added below

  notes              text                          NULL,

  created_at         timestamptz                   NOT NULL DEFAULT now(),
  updated_at         timestamptz                   NOT NULL DEFAULT now(),
  created_by         uuid                          NULL,
  updated_by         uuid                          NULL,

  CONSTRAINT attendance_minutes_nonneg CHECK (total_minutes >= 0 AND break_minutes >= 0),
  CONSTRAINT attendance_out_after_in   CHECK (check_out_at IS NULL OR check_in_at IS NULL OR check_out_at >= check_in_at)
);

CREATE UNIQUE INDEX attendance_emp_date_uq
  ON attendance_records (employee_id, attendance_date);

CREATE INDEX attendance_date_idx   ON attendance_records (attendance_date, status);
CREATE INDEX attendance_status_idx ON attendance_records (status, attendance_date);

CREATE TRIGGER attendance_records_audit
  BEFORE INSERT OR UPDATE ON attendance_records
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- attendance_punches ---------------------------------------------
-- Raw punch event stream. Append-only. The summary is derived from this table
-- by the scheduled aggregation job. Kept separate so we can keep biometric/
-- kiosk events forever for compliance even after the daily record is closed.
CREATE TABLE attendance_punches (
  id            uuid                      PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id   uuid                      NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  punched_at    timestamptz               NOT NULL,
  punch_type    worktrack.punch_type      NOT NULL,
  source        worktrack.punch_source    NOT NULL,
  device_id     text                      NULL,    -- biometric device serial, kiosk id
  ip            inet                      NULL,
  latitude      numeric(9, 6)             NULL,
  longitude     numeric(9, 6)             NULL,
  is_valid      boolean                   NOT NULL DEFAULT true,    -- false if rejected as duplicate
  raw_payload   jsonb                     NULL,
  created_at    timestamptz               NOT NULL DEFAULT now()
);

CREATE INDEX attendance_punches_emp_time_idx ON attendance_punches (employee_id, punched_at DESC);
CREATE INDEX attendance_punches_time_idx     ON attendance_punches (punched_at DESC);
CREATE INDEX attendance_punches_device_idx   ON attendance_punches (device_id, punched_at DESC) WHERE device_id IS NOT NULL;


-- ---------- attendance_corrections -----------------------------------------
-- Employee-initiated request to fix an attendance record. The original and
-- proposed states are stored as jsonb so the review UI can diff them, and so
-- approvals can be replayed if the materialized record needs rebuilding.
CREATE TABLE attendance_corrections (
  id                 uuid                          PRIMARY KEY DEFAULT gen_random_uuid(),
  attendance_record_id uuid                        NOT NULL REFERENCES attendance_records(id) ON DELETE CASCADE,
  employee_id        uuid                          NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  reason             text                          NOT NULL,
  original_snapshot  jsonb                         NOT NULL,
  proposed_snapshot  jsonb                         NOT NULL,
  status             worktrack.correction_status   NOT NULL DEFAULT 'pending',
  decided_by         uuid                          NULL REFERENCES employees(id) ON DELETE SET NULL,
  decided_at         timestamptz                   NULL,
  decision_note      text                          NULL,
  requested_at       timestamptz                   NOT NULL DEFAULT now(),
  created_at         timestamptz                   NOT NULL DEFAULT now(),
  updated_at         timestamptz                   NOT NULL DEFAULT now(),

  CONSTRAINT corrections_decision_consistency CHECK (
    (status IN ('pending', 'cancelled') AND decided_at IS NULL AND decided_by IS NULL) OR
    (status IN ('approved', 'denied') AND decided_at IS NOT NULL AND decided_by IS NOT NULL)
  )
);
CREATE INDEX attendance_corrections_emp_idx       ON attendance_corrections (employee_id, requested_at DESC);
CREATE INDEX attendance_corrections_pending_idx   ON attendance_corrections (requested_at DESC) WHERE status = 'pending';
CREATE INDEX attendance_corrections_record_idx    ON attendance_corrections (attendance_record_id);

CREATE TRIGGER attendance_corrections_touch
  BEFORE UPDATE ON attendance_corrections
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- holidays -------------------------------------------------------
-- One row per holiday per location. NULL location = company-wide.
CREATE TABLE holidays (
  id           uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text          NOT NULL,
  holiday_date date          NOT NULL,
  location_id  uuid          NULL REFERENCES locations(id) ON DELETE CASCADE,
  holiday_type text          NULL,        -- 'national' | 'regional' | 'optional' | 'company'
  is_optional  boolean       NOT NULL DEFAULT false,
  notes        text          NULL,
  created_at   timestamptz   NOT NULL DEFAULT now(),
  updated_at   timestamptz   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX holidays_uq
  ON holidays (holiday_date, COALESCE(location_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX holidays_date_idx ON holidays (holiday_date);

-- Now wire attendance_records.holiday_id
ALTER TABLE attendance_records
  ADD CONSTRAINT attendance_holiday_fk
  FOREIGN KEY (holiday_id) REFERENCES holidays(id) ON DELETE SET NULL;
