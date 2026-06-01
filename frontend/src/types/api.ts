/** TypeScript types mirroring api/openapi-v1.yaml (hand-authored for v1). */

export type Role = "admin" | "manager" | "employee" | "viewer";

export interface User {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Me {
  user: User;
  employee: null; // reserved for a future embedded employee object
  employee_id: string | null; // linked employee profile, if any
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string | null;
  };
}
