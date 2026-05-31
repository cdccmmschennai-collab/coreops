-- =============================================================
-- WorkTrack — Cross-cutting indexes, views, retention helpers
-- 09_indexes_views.sql
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- Soft-delete helper view ---------------------------------------
-- Every "live" query reads from these instead of the raw tables when the
-- application has a soft-delete column. Keeps callers honest.
CREATE OR REPLACE VIEW v_employees      AS SELECT * FROM employees      WHERE deleted_at IS NULL;
CREATE OR REPLACE VIEW v_projects       AS SELECT * FROM projects       WHERE deleted_at IS NULL;
CREATE OR REPLACE VIEW v_daily_reports  AS SELECT * FROM daily_reports  WHERE deleted_at IS NULL;
CREATE OR REPLACE VIEW v_leave_requests AS SELECT * FROM leave_requests WHERE deleted_at IS NULL;

-- ---------- Manager hierarchy (recursive) ---------------------------------
-- Returns (descendant, ancestor, depth) for every manager-employee pair.
-- Useful for "report queue for my org" queries up to N levels deep.
CREATE OR REPLACE VIEW v_employee_org AS
WITH RECURSIVE org AS (
  SELECT id AS descendant, manager_id AS ancestor, 1 AS depth
    FROM employees
   WHERE manager_id IS NOT NULL AND deleted_at IS NULL
  UNION ALL
  SELECT o.descendant, e.manager_id, o.depth + 1
    FROM org o
    JOIN employees e ON e.id = o.ancestor AND e.deleted_at IS NULL
   WHERE e.manager_id IS NOT NULL AND o.depth < 12
)
SELECT * FROM org;


-- ---------- Daily report dashboard view ----------------------------------
-- Drives the employee Home dashboard. Reads `daily_reports` + `employees` +
-- `attendance_records` for the date.
CREATE OR REPLACE VIEW v_employee_today AS
SELECT
  e.id            AS employee_id,
  e.display_name,
  e.manager_id,
  dr.id           AS report_id,
  dr.report_date,
  dr.status       AS report_status,
  dr.total_hours,
  dr.total_tasks_done,
  ar.status       AS attendance_status,
  ar.check_in_at,
  ar.check_out_at
FROM employees e
LEFT JOIN daily_reports dr
       ON dr.employee_id = e.id
      AND dr.report_date = current_date
      AND dr.deleted_at IS NULL
LEFT JOIN attendance_records ar
       ON ar.employee_id = e.id
      AND ar.attendance_date = current_date
WHERE e.deleted_at IS NULL
  AND e.employment_status IN ('active', 'on_leave');


-- ---------- Manager review queue ------------------------------------------
-- Pending reports the manager owes a decision on.
CREATE OR REPLACE VIEW v_manager_review_queue AS
SELECT
  dr.id, dr.employee_id, dr.report_date, dr.status,
  dr.total_hours, dr.submitted_at,
  e.manager_id AS reviewer_id,
  e.display_name AS employee_name
FROM daily_reports dr
JOIN employees e ON e.id = dr.employee_id AND e.deleted_at IS NULL
WHERE dr.deleted_at IS NULL
  AND dr.status IN ('submitted', 'in_review');


-- ---------- Notification badge ---------------------------------------------
-- Cheap unread count per recipient — used on every page load.
CREATE OR REPLACE VIEW v_unread_notifications AS
SELECT recipient_employee_id, count(*) AS unread_count
  FROM notification_recipients
 WHERE channel = 'in_app'
   AND read_at IS NULL
   AND dismissed_at IS NULL
 GROUP BY recipient_employee_id;


-- ---------- Recommended composite indexes (cross-table review) ------------
-- Most are already created next to their tables; these are the secondary
-- indexes added after observing query patterns.

-- Daily reports — fast lookup of "did this employee submit on this date?"
-- The unique index in 04 already covers it; documented here so onboarding
-- engineers don't add a duplicate.

-- Audit log — combined actor + action filter used by HR search.
CREATE INDEX IF NOT EXISTS audit_logs_actor_action_idx
  ON worktrack_audit.audit_logs (actor_user_id, action, occurred_at DESC);


-- ---------- Retention helpers ---------------------------------------------
-- Examples — wire into a cron/pg_cron job.

-- Drop login attempts older than 180 days.
CREATE OR REPLACE FUNCTION worktrack.purge_old_login_attempts(p_days int DEFAULT 180)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  DELETE FROM auth_login_attempts WHERE attempted_at < now() - (p_days || ' days')::interval;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END;
$$;

-- Mark notifications as auto-dismissed after 90 days.
CREATE OR REPLACE FUNCTION worktrack.autodismiss_notifications(p_days int DEFAULT 90)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  UPDATE notification_recipients
     SET dismissed_at = now()
   WHERE channel = 'in_app'
     AND dismissed_at IS NULL
     AND created_at < now() - (p_days || ' days')::interval;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END;
$$;
