/** TypeScript types mirroring api/openapi-v1.yaml (hand-authored for v1). */

export type Role = "project_manager" | "employee";

export interface User {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export type EmployeeStatus = "active" | "on_leave" | "exited";

/**
 * Business identity embedded in /auth/me. Manager and office are resolved to
 * display names server-side (an employee cannot read those rows directly).
 */
export interface EmployeeProfile {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  work_email: string | null;
  personal_email: string | null;
  phone: string | null;
  department: string | null;
  designation: string | null;
  manager_id: string | null;
  manager_name: string | null;
  office_id: string | null;
  office_name: string | null;
  date_of_joining: string | null;
  status: EmployeeStatus;
}

export interface Me {
  user: User;
  employee: EmployeeProfile | null; // linked business identity, if any
  employee_id: string | null; // linked employee profile id, if any
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ChangePasswordBody {
  current_password: string;
  new_password: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string | null;
  };
}
