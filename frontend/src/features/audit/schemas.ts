// Human-readable labels + filter options for audit actions.
// Keep in sync with backend app/modules/audit/constants.py (AuditAction).

export const ACTION_LABEL: Record<string, string> = {
  "auth.login.success": "Login",
  "auth.login.failure": "Login failed",
  "auth.login.rate_limited": "Login throttled",
  "auth.logout": "Logout",
  "auth.password.change_self": "Changed own password",
  "user.create": "User created",
  "user.role.change": "Role changed",
  "user.status.change": "Account status changed",
  "user.password.reset_admin": "Password reset (admin)",
  "employee.account.link": "Account linked",
  "employee.account.relink": "Account relinked",
  "employee.account.unlink": "Account unlinked",
  "employee.create": "Employee created",
  "employee.update": "Employee updated",
  "employee.deactivate": "Employee deactivated",
  "project.member.add": "Project member added",
  "project.member.role_change": "Project role changed",
  "project.member.remove": "Project member removed",
};

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action;
}

export const ACTION_OPTIONS = Object.keys(ACTION_LABEL);

export const ENTITY_OPTIONS = ["user", "employee", "project", "project_member"];

export const STATUS_OPTIONS = ["success", "failure"];
