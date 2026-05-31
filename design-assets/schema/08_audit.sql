-- =============================================================
-- WorkTrack — Audit log (monthly partitioned)
-- 08_audit.sql
--
-- The audit log is the highest-volume table in the system. We partition by
-- month on the (timestamp) column so old months can be detached and shipped
-- to cold storage. The table lives in the worktrack_audit schema so it can
-- be granted independently.
-- =============================================================
SET search_path TO worktrack_audit, worktrack, public;

-- ---------- audit_logs (parent) --------------------------------------------
-- Append-only (the only DML the app issues is INSERT). Reads are by actor,
-- by object, and by time range.
CREATE TABLE worktrack_audit.audit_logs (
  id              bigserial      NOT NULL,
  occurred_at     timestamptz    NOT NULL DEFAULT now(),

  -- Actor
  actor_user_id     uuid         NULL,           -- auth_users.id; NULL for 'system'
  actor_employee_id uuid         NULL,           -- employees.id  (denorm for reporting)
  actor_label       text         NULL,           -- 'system' | 'integration:slack' | etc

  -- Action — verbs in past tense. Examples:
  --   'login.succeeded', 'login.failed', 'report.submitted', 'report.reviewed',
  --   'leave.approved', 'leave.denied', 'attendance.corrected',
  --   'employee.created', 'role.assigned', 'project.archived'.
  action          text           NOT NULL,

  -- Target object
  object_type     text           NULL,           -- 'daily_report' | 'leave_request' | 'employee' | …
  object_id       uuid           NULL,
  object_label    text           NULL,           -- denorm display label

  -- Snapshot — diff or before/after. The application is free to put either:
  --   { "before": {...}, "after": {...} }
  --   { "diff":   {...} }
  --   { "context": {...} }
  payload         jsonb          NOT NULL DEFAULT '{}'::jsonb,

  -- Context
  ip              inet           NULL,
  user_agent      text           NULL,
  request_id      uuid           NULL,           -- traces back to API gateway
  session_id      uuid           NULL REFERENCES worktrack.auth_sessions(id) ON DELETE SET NULL,

  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

-- Hot read paths:
CREATE INDEX audit_logs_actor_time_idx  ON worktrack_audit.audit_logs (actor_user_id, occurred_at DESC);
CREATE INDEX audit_logs_object_time_idx ON worktrack_audit.audit_logs (object_type, object_id, occurred_at DESC);
CREATE INDEX audit_logs_action_time_idx ON worktrack_audit.audit_logs (action, occurred_at DESC);
CREATE INDEX audit_logs_time_idx        ON worktrack_audit.audit_logs (occurred_at DESC);
CREATE INDEX audit_logs_payload_gin     ON worktrack_audit.audit_logs USING gin (payload jsonb_path_ops);


-- ---------- Default & first partitions -------------------------------------
-- Production: maintain N+2 partitions ahead via pg_partman or a cron job.
CREATE TABLE worktrack_audit.audit_logs_default
  PARTITION OF worktrack_audit.audit_logs DEFAULT;

CREATE TABLE worktrack_audit.audit_logs_2026_05
  PARTITION OF worktrack_audit.audit_logs
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE worktrack_audit.audit_logs_2026_06
  PARTITION OF worktrack_audit.audit_logs
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE worktrack_audit.audit_logs_2026_07
  PARTITION OF worktrack_audit.audit_logs
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');


-- ---------- audit_logs_archive_meta ----------------------------------------
-- Bookkeeping for the partition-detach job. Each detached partition is
-- recorded here with the destination (S3 URI, glacier vault id, etc).
CREATE TABLE worktrack_audit.audit_logs_archive_meta (
  partition_name   text          PRIMARY KEY,
  range_start      date          NOT NULL,
  range_end        date          NOT NULL,
  row_count        bigint        NULL,
  archived_at      timestamptz   NULL,
  archive_uri      text          NULL,
  notes            text          NULL
);


-- ---------- Convenience helper to insert audit events ----------------------
-- The app is free to INSERT directly; this is offered for psql tooling and
-- for trigger-based capture in stored procedures.
CREATE OR REPLACE FUNCTION worktrack_audit.log_event(
  p_action       text,
  p_object_type  text,
  p_object_id    uuid,
  p_object_label text DEFAULT NULL,
  p_payload      jsonb DEFAULT '{}'::jsonb
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE new_id bigint;
BEGIN
  INSERT INTO worktrack_audit.audit_logs (
    actor_user_id, actor_employee_id,
    action, object_type, object_id, object_label, payload
  ) VALUES (
    worktrack.current_user_id(),
    NULL,
    p_action, p_object_type, p_object_id, p_object_label, p_payload
  ) RETURNING id INTO new_id;
  RETURN new_id;
END;
$$;
