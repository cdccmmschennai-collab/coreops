"""Canonical audit action + entity-type constants.

Single source of truth so emitting services and the frontend filter share the
same vocabulary. Actions are dotted: `<domain>.<thing>.<verb>`.
"""


class EntityType:
    USER = "user"
    EMPLOYEE = "employee"
    PROJECT = "project"
    PROJECT_MEMBER = "project_member"
    TASK = "task"


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

    # --- task assignment & lifecycle (Tier B) ---
    TASK_ASSIGN = "task.assign"
    TASK_COMPLETE = "task.complete"
    TASK_STATUS_CHANGE = "task.status.change"
    TASK_CANCEL = "task.cancel"


# Statuses
STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
