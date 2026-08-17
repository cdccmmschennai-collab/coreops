"""Canonical audit action + entity-type constants.

Single source of truth so emitting services and the frontend filter share the
same vocabulary. Actions are dotted: `<domain>.<thing>.<verb>`.
"""


class EntityType:
    USER = "user"
    EMPLOYEE = "employee"
    PROJECT = "project"
    PROJECT_MEMBER = "project_member"
    DELIVERABLE = "deliverable"
    TASK = "task"
    ACTIVITY = "activity"
    BIOMETRIC_SYNC_BATCH = "biometric_sync_batch"
    BIOMETRIC_MAPPING = "biometric_employee_mapping"
    ATTENDANCE_RECORD = "attendance_record"
    LEAVE_REQUEST = "leave_request"


class AuditAction:
    # --- auth (Tier A) ---
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGIN_RATE_LIMITED = "auth.login.rate_limited"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGE_SELF = "auth.password.change_self"

    # --- user identity (Tier A) ---
    USER_CREATE = "user.create"
    USER_ROLE_CHANGE = "user.role.change"
    USER_STATUS_CHANGE = "user.status.change"
    USER_PASSWORD_RESET = "user.password.reset_admin"

    # --- employee account linkage (Tier A) ---
    EMPLOYEE_ACCOUNT_LINK = "employee.account.link"
    EMPLOYEE_ACCOUNT_RELINK = "employee.account.relink"
    EMPLOYEE_ACCOUNT_UNLINK = "employee.account.unlink"

    # --- employee lifecycle (Tier B) ---
    EMPLOYEE_CREATE = "employee.create"
    EMPLOYEE_UPDATE = "employee.update"
    EMPLOYEE_DEACTIVATE = "employee.deactivate"

    # --- project membership (Tier B) ---
    PROJECT_MEMBER_ADD = "project.member.add"
    PROJECT_MEMBER_ROLE_CHANGE = "project.member.role_change"
    PROJECT_MEMBER_REMOVE = "project.member.remove"

    # --- project dates (Tier B) ---
    PROJECT_PLANNED_DATE_CHANGE = "project.planned_date.change"

    # --- deliverable change tracking (Tier B) ---
    DELIVERABLE_FIELD_CHANGE = "deliverable.field.change"

    # --- task assignment & lifecycle (Tier B) ---
    TASK_ASSIGN = "task.assign"
    TASK_COMPLETE = "task.complete"
    TASK_STATUS_CHANGE = "task.status.change"
    TASK_CANCEL = "task.cancel"

    # --- activity access control (Tier B, migration 0061) ---
    ACTIVITY_ACCESS_TYPE_CHANGED = "activity.access.type_change"
    ACTIVITY_ACCESS_GRANTED = "activity.access.grant"
    ACTIVITY_ACCESS_REVOKED = "activity.access.revoke"

    # --- biometric ingestion (Tier B, migration 0066) ---
    # Deliberately event-level, NOT per punch: a successful batch of 500 punches
    # emits zero audit rows, only the structured ingestion log line. Audit is
    # reserved for security-relevant or operator-actionable events.
    BIOMETRIC_CONNECTOR_AUTH_FAILED = "biometric.connector.auth_failure"
    BIOMETRIC_BATCH_FAILED = "biometric.batch.failed"
    BIOMETRIC_BATCH_UNMAPPED_HIGH = "biometric.batch.unmapped_high"
    BIOMETRIC_MAPPING_CREATED = "biometric.mapping.create"
    BIOMETRIC_MAPPING_CHANGED = "biometric.mapping.change"
    BIOMETRIC_MAPPING_DEACTIVATED = "biometric.mapping.deactivate"

    # --- official attendance decisions (Tier B) ---
    # A human overriding what a day means is exactly the kind of act an audit log
    # exists for: biometric evidence is immutable, so the ONLY way a day's meaning
    # changes is somebody deciding it did. `details` carries the previous and new
    # status, the times, and the PM's note.
    ATTENDANCE_RECORD_CREATE = "attendance.record.create"
    ATTENDANCE_RECORD_UPDATE = "attendance.record.update"
    ATTENDANCE_RECORD_DELETE = "attendance.record.delete"

    # --- leave decisions (Tier B, Phase 10) ---
    # An approval moves real state: it marks calendar days Leave and draws down a
    # balance. Before Phase 10 the only trace of a decision was the denormalised
    # `manager_id` / `manager_comment` on the row itself, which records WHO but
    # not WHAT CHANGED and is overwritten by the next decision. These rows carry
    # the day count, the dates and the balance movement, so a leave decision can
    # be reconstructed after the request row has moved on.
    LEAVE_REQUEST_APPROVE = "leave.request.approve"
    LEAVE_REQUEST_REJECT = "leave.request.reject"
    LEAVE_REQUEST_CANCEL = "leave.request.cancel"
    LEAVE_CANCELLATION_REQUEST = "leave.cancellation.request"
    LEAVE_CANCELLATION_APPROVE = "leave.cancellation.approve"
    LEAVE_CANCELLATION_REJECT = "leave.cancellation.reject"


# Statuses
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
