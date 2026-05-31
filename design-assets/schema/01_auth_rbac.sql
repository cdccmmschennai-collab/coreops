-- =============================================================
-- WorkTrack — Authentication & RBAC
-- 01_auth_rbac.sql
-- =============================================================
SET search_path TO worktrack, public;

-- ---------- auth_users -----------------------------------------------------
-- Identity record. Decoupled from `employees` so non-employee identities
-- (e.g. service accounts, external auditors, ex-employees we still need to
-- authenticate for offboarding flows) can exist without an employee row.
CREATE TABLE auth_users (
  id                     uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  email                  citext        NOT NULL,
  password_hash          text          NULL,                -- NULL for SSO-only accounts
  password_changed_at    timestamptz   NULL,
  is_sso_only            boolean       NOT NULL DEFAULT false,
  sso_provider           text          NULL,                -- 'okta', 'google', 'azure_ad'
  sso_subject            text          NULL,                -- provider's stable user id

  mfa_enabled            boolean       NOT NULL DEFAULT false,
  mfa_secret_encrypted   bytea         NULL,                -- application-layer encrypted

  failed_login_count     integer       NOT NULL DEFAULT 0,
  locked_until           timestamptz   NULL,
  last_login_at          timestamptz   NULL,
  last_login_ip          inet          NULL,

  is_active              boolean       NOT NULL DEFAULT true,

  created_at             timestamptz   NOT NULL DEFAULT now(),
  updated_at             timestamptz   NOT NULL DEFAULT now(),
  created_by             uuid          NULL,
  updated_by             uuid          NULL,
  deleted_at             timestamptz   NULL,

  CONSTRAINT auth_users_email_format CHECK (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  CONSTRAINT auth_users_sso_fields   CHECK (
    (is_sso_only = false) OR (sso_provider IS NOT NULL AND sso_subject IS NOT NULL)
  )
);

CREATE UNIQUE INDEX auth_users_email_uq
  ON auth_users (email) WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX auth_users_sso_uq
  ON auth_users (sso_provider, sso_subject)
  WHERE sso_provider IS NOT NULL AND deleted_at IS NULL;

CREATE TRIGGER auth_users_audit
  BEFORE INSERT OR UPDATE ON auth_users
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_audit_fields();


-- ---------- auth_sessions --------------------------------------------------
-- One row per active web session / refresh token. We only store the SHA-256
-- of the token; the raw token never round-trips through the database.
CREATE TABLE auth_sessions (
  id                uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid          NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  token_hash        bytea         NOT NULL,            -- sha256(token)
  refresh_hash      bytea         NULL,                -- optional refresh
  ip                inet          NULL,
  user_agent        text          NULL,
  device_label      text          NULL,                -- "Chrome on MacOS"
  issued_at         timestamptz   NOT NULL DEFAULT now(),
  expires_at        timestamptz   NOT NULL,
  last_seen_at      timestamptz   NOT NULL DEFAULT now(),
  revoked_at        timestamptz   NULL,
  revoked_reason    text          NULL
);

CREATE UNIQUE INDEX auth_sessions_token_uq    ON auth_sessions (token_hash);
CREATE INDEX        auth_sessions_user_idx    ON auth_sessions (user_id) WHERE revoked_at IS NULL;
CREATE INDEX        auth_sessions_expiry_idx  ON auth_sessions (expires_at) WHERE revoked_at IS NULL;


-- ---------- auth_password_resets ------------------------------------------
CREATE TABLE auth_password_resets (
  id          uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid         NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  token_hash  bytea        NOT NULL,
  expires_at  timestamptz  NOT NULL,
  used_at     timestamptz  NULL,
  ip          inet         NULL,
  created_at  timestamptz  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX auth_pwreset_token_uq ON auth_password_resets (token_hash);
CREATE INDEX auth_pwreset_user_idx ON auth_password_resets (user_id, created_at DESC);


-- ---------- auth_login_attempts -------------------------------------------
-- Append-only. Read for rate-limiting and security analytics.
CREATE TABLE auth_login_attempts (
  id              bigserial    PRIMARY KEY,
  email_attempted citext       NOT NULL,
  user_id         uuid         NULL REFERENCES auth_users(id) ON DELETE SET NULL,
  succeeded       boolean      NOT NULL,
  reason          text         NULL,    -- 'bad_password' | 'mfa_failed' | 'locked' | 'sso_mismatch'
  ip              inet         NULL,
  user_agent      text         NULL,
  attempted_at    timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX auth_login_attempts_email_idx ON auth_login_attempts (email_attempted, attempted_at DESC);
CREATE INDEX auth_login_attempts_ip_idx    ON auth_login_attempts (ip,             attempted_at DESC);


-- ==========================================================================
-- RBAC
-- ==========================================================================

-- ---------- roles ----------------------------------------------------------
-- System roles are immutable; tenant-defined roles can be added.
CREATE TABLE roles (
  id              uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  key             text         NOT NULL,    -- 'admin', 'manager', 'employee', 'hr', 'viewer'
  name            text         NOT NULL,
  description     text         NULL,
  is_system_role  boolean      NOT NULL DEFAULT false,
  created_at      timestamptz  NOT NULL DEFAULT now(),
  updated_at      timestamptz  NOT NULL DEFAULT now(),
  deleted_at      timestamptz  NULL
);
CREATE UNIQUE INDEX roles_key_uq ON roles (key) WHERE deleted_at IS NULL;

CREATE TRIGGER roles_touch BEFORE UPDATE ON roles
  FOR EACH ROW EXECUTE FUNCTION worktrack.tg_set_updated_at();


-- ---------- permissions ----------------------------------------------------
-- Dotted keys like 'report.submit', 'report.review', 'leave.approve',
-- 'attendance.correct', 'admin.audit_log', 'employee.invite'.
CREATE TABLE permissions (
  id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  key          text         NOT NULL,
  description  text         NULL,
  created_at   timestamptz  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX permissions_key_uq ON permissions (key);


-- ---------- role_permissions -----------------------------------------------
CREATE TABLE role_permissions (
  role_id        uuid         NOT NULL REFERENCES roles(id)       ON DELETE CASCADE,
  permission_id  uuid         NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  granted_at     timestamptz  NOT NULL DEFAULT now(),
  PRIMARY KEY (role_id, permission_id)
);
CREATE INDEX role_permissions_permission_idx ON role_permissions (permission_id);


-- ---------- user_roles -----------------------------------------------------
-- A user may have the same role at different scopes (e.g. "manager of Platform"
-- and "manager of Mobile"). scope_id is the FK target id in the relevant table
-- and is interpreted alongside scope_type.
CREATE TABLE user_roles (
  id           uuid                   PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid                   NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  role_id      uuid                   NOT NULL REFERENCES roles(id)      ON DELETE RESTRICT,
  scope_type   worktrack.rbac_scope   NOT NULL DEFAULT 'global',
  scope_id     uuid                   NULL,    -- FK target depends on scope_type
  granted_by   uuid                   NULL REFERENCES auth_users(id) ON DELETE SET NULL,
  granted_at   timestamptz            NOT NULL DEFAULT now(),
  expires_at   timestamptz            NULL,
  revoked_at   timestamptz            NULL,

  CONSTRAINT user_roles_scope_id_required CHECK (
    (scope_type = 'global' AND scope_id IS NULL) OR
    (scope_type <> 'global' AND scope_id IS NOT NULL)
  )
);
CREATE UNIQUE INDEX user_roles_uniq
  ON user_roles (user_id, role_id, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid))
  WHERE revoked_at IS NULL;
CREATE INDEX user_roles_user_idx ON user_roles (user_id) WHERE revoked_at IS NULL;
CREATE INDEX user_roles_role_idx ON user_roles (role_id) WHERE revoked_at IS NULL;
