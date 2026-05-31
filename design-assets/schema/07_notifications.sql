-- =============================================================
-- WorkTrack — Notifications
-- 07_notifications.sql
--
-- Two-table model: notifications (the canonical event) and
-- notification_recipients (per-channel, per-user delivery state).
--
-- A single business event (e.g. "leave approved") creates one notifications
-- row plus N recipient rows (in-app + email + push). Subjects of the event
-- (a leave_request, a daily_report, an attendance_correction) are referenced
-- as polymorphic subject_type / subject_id; we deliberately don't FK these so
-- subject tables can soft-delete without dropping their notification history.
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- notification_templates -----------------------------------------
-- Admin-editable templates. The application picks a template by `key` and
-- merges `data_json` from the notifications row to render title/body.
CREATE TABLE notification_templates (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  key             text          NOT NULL,    -- 'report.due', 'leave.approved'
  name            text          NOT NULL,
  description     text          NULL,
  default_priority worktrack.notification_priority NOT NULL DEFAULT 'normal',
  default_channels worktrack.notification_channel[] NOT NULL DEFAULT ARRAY['in_app']::worktrack.notification_channel[],
  title_template  text          NOT NULL,
  body_template   text          NOT NULL,
  is_system       boolean       NOT NULL DEFAULT false,
  is_active       boolean       NOT NULL DEFAULT true,
  created_at      timestamptz   NOT NULL DEFAULT now(),
  updated_at      timestamptz   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX notification_templates_key_uq ON notification_templates (key);
CREATE TRIGGER notification_templates_touch BEFORE UPDATE ON notification_templates
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- notifications --------------------------------------------------
-- The canonical event. One row per business event regardless of fan-out.
CREATE TABLE notifications (
  id              uuid                                PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id     uuid                                NOT NULL REFERENCES notification_templates(id) ON DELETE RESTRICT,
  template_key    text                                NOT NULL,    -- denormalized for fast read

  -- Polymorphic reference to the subject (e.g. a leave_request or a
  -- daily_report). Not FK'd — see file header.
  subject_type    text                                NULL,        -- 'leave_request' | 'daily_report' | 'attendance_correction' | 'project'
  subject_id      uuid                                NULL,

  -- Cached materialized title/body (after template rendering). Stored so we
  -- can edit templates later without rewriting past notifications.
  title           text                                NOT NULL,
  body            text                                NOT NULL,
  cta_label       text                                NULL,
  cta_route       text                                NULL,        -- 'report' | 'attendance' | etc — matches UI routes

  data            jsonb                               NOT NULL DEFAULT '{}'::jsonb,    -- variable bag

  priority        worktrack.notification_priority     NOT NULL DEFAULT 'normal',

  -- The actor that caused the event (NULL for system-generated events).
  actor_employee_id uuid                              NULL REFERENCES employees(id) ON DELETE SET NULL,

  created_at      timestamptz                         NOT NULL DEFAULT now()
);

CREATE INDEX notifications_subject_idx ON notifications (subject_type, subject_id) WHERE subject_type IS NOT NULL;
CREATE INDEX notifications_created_idx ON notifications (created_at DESC);
CREATE INDEX notifications_template_idx ON notifications (template_key, created_at DESC);


-- ---------- notification_recipients ----------------------------------------
-- Per-user per-channel delivery state. Almost every read of notifications
-- goes through this table; the inbox/badge query is the busiest one in the
-- system and is what most of the indexes below are tuned for.
CREATE TABLE notification_recipients (
  id              uuid                                PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_id uuid                                NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  recipient_employee_id uuid                          NOT NULL REFERENCES employees(id)     ON DELETE CASCADE,
  channel         worktrack.notification_channel      NOT NULL,

  -- Delivery
  delivery_status worktrack.delivery_status           NOT NULL DEFAULT 'pending',
  delivered_at    timestamptz                         NULL,
  failed_reason   text                                NULL,
  retry_count     integer                             NOT NULL DEFAULT 0,

  -- Engagement
  read_at         timestamptz                         NULL,
  clicked_at      timestamptz                         NULL,
  dismissed_at    timestamptz                         NULL,

  created_at      timestamptz                         NOT NULL DEFAULT now(),
  updated_at      timestamptz                         NOT NULL DEFAULT now()
);

-- A single recipient row per (notification, recipient, channel).
CREATE UNIQUE INDEX notification_recipients_uq
  ON notification_recipients (notification_id, recipient_employee_id, channel);

-- Inbox + unread badge — hottest read path. Partial index keeps it tiny.
CREATE INDEX notification_recipients_inbox_idx
  ON notification_recipients (recipient_employee_id, created_at DESC)
  WHERE channel = 'in_app' AND dismissed_at IS NULL;

CREATE INDEX notification_recipients_unread_idx
  ON notification_recipients (recipient_employee_id)
  WHERE channel = 'in_app' AND read_at IS NULL AND dismissed_at IS NULL;

-- Outbound queue for email/push workers: oldest pending first.
CREATE INDEX notification_recipients_outbound_idx
  ON notification_recipients (channel, created_at)
  WHERE delivery_status = 'pending' AND channel <> 'in_app';

CREATE TRIGGER notification_recipients_touch
  BEFORE UPDATE ON notification_recipients
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- notification_preferences ---------------------------------------
-- Per-user opt-in/out per channel. NULL = inherit defaults.
CREATE TABLE notification_preferences (
  employee_id     uuid                                NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  template_id     uuid                                NOT NULL REFERENCES notification_templates(id) ON DELETE CASCADE,
  channel         worktrack.notification_channel      NOT NULL,
  enabled         boolean                             NOT NULL DEFAULT true,
  updated_at      timestamptz                         NOT NULL DEFAULT now(),
  PRIMARY KEY (employee_id, template_id, channel)
);
CREATE INDEX notification_preferences_emp_idx ON notification_preferences (employee_id);

CREATE TRIGGER notification_preferences_touch
  BEFORE UPDATE ON notification_preferences
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();
