-- =============================================================
-- WorkTrack — Master DDL runner
-- Apply in order. Idempotent only on first run; for re-application,
-- use migrations.
-- =============================================================
\i 00_setup.sql
\i 01_auth_rbac.sql
\i 02_employees.sql
\i 03_projects.sql
\i 04_daily_reports.sql
\i 05_attendance.sql
\i 06_leave.sql
\i 07_notifications.sql
\i 08_audit.sql
\i 09_indexes_views.sql
