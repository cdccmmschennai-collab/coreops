-- =============================================================
-- WorkTrack — Database setup
-- 00_setup.sql · extensions, shared helpers, enums
-- PostgreSQL 14+
-- =============================================================

-- ---------- Extensions -----------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "citext";     -- case-insensitive email
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- composite indexes on jsonb + scalar

-- All entities live in the worktrack schema; the audit log lives in its own
-- schema so it can be granted/partitioned independently.
CREATE SCHEMA IF NOT EXISTS worktrack;
CREATE SCHEMA IF NOT EXISTS worktrack_audit;
SET search_path TO worktrack, public;


-- ---------- Shared trigger: bump updated_at on UPDATE ----------------------
CREATE OR REPLACE FUNCTION worktrack.tg_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;


-- ---------- Shared trigger: stamp updated_by from session ------------------
-- App is expected to SET LOCAL worktrack.current_user_id = '<uuid>'
-- at the start of every transaction.
CREATE OR REPLACE FUNCTION worktrack.current_user_id()
RETURNS uuid
LANGUAGE plpgsql STABLE AS $$
DECLARE v text;
BEGIN
  v := current_setting('worktrack.current_user_id', true);
  IF v IS NULL OR v = '' THEN RETURN NULL; END IF;
  RETURN v::uuid;
END;
$$;

CREATE OR REPLACE FUNCTION worktrack.tg_set_audit_fields()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    NEW.created_at := COALESCE(NEW.created_at, now());
    NEW.updated_at := COALESCE(NEW.updated_at, now());
    IF NEW.created_by IS NULL THEN NEW.created_by := worktrack.current_user_id(); END IF;
    IF NEW.updated_by IS NULL THEN NEW.updated_by := NEW.created_by; END IF;
  ELSIF TG_OP = 'UPDATE' THEN
    NEW.updated_at := now();
    NEW.updated_by := COALESCE(worktrack.current_user_id(), NEW.updated_by);
  END IF;
  RETURN NEW;
END;
$$;


-- ---------- Enums ----------------------------------------------------------
-- Use enums for closed sets that we never expect non-engineering users to
-- extend at runtime. Anything admins might add (activity types, leave types,
-- notification templates) is a lookup table instead.

CREATE TYPE worktrack.employment_status AS ENUM (
  'active', 'on_leave', 'suspended', 'exited'
);

CREATE TYPE worktrack.employment_type AS ENUM (
  'full_time', 'part_time', 'contractor', 'intern'
);

CREATE TYPE worktrack.day_status AS ENUM (
  'working', 'half_day', 'wfh', 'leave', 'comp_off', 'holiday'
);

CREATE TYPE worktrack.report_status AS ENUM (
  'draft', 'submitted', 'in_review', 'approved', 'rejected'
);

CREATE TYPE worktrack.attendance_status AS ENUM (
  'present', 'wfh', 'leave', 'comp_off', 'half_day',
  'holiday', 'weekend', 'absent'
);

CREATE TYPE worktrack.punch_type AS ENUM ('in', 'out');

CREATE TYPE worktrack.punch_source AS ENUM (
  'web', 'mobile', 'biometric', 'kiosk', 'manual', 'system'
);

CREATE TYPE worktrack.leave_request_status AS ENUM (
  'draft', 'pending', 'approved', 'denied', 'cancelled', 'withdrawn'
);

CREATE TYPE worktrack.correction_status AS ENUM (
  'pending', 'approved', 'denied', 'cancelled'
);

CREATE TYPE worktrack.project_status AS ENUM (
  'draft', 'active', 'at_risk', 'on_hold', 'completed', 'archived'
);

CREATE TYPE worktrack.notification_priority AS ENUM (
  'low', 'normal', 'high', 'urgent'
);

CREATE TYPE worktrack.notification_channel AS ENUM (
  'in_app', 'email', 'push', 'sms'
);

CREATE TYPE worktrack.delivery_status AS ENUM (
  'pending', 'sent', 'failed', 'skipped'
);

CREATE TYPE worktrack.rbac_scope AS ENUM (
  'global', 'department', 'project', 'self'
);
