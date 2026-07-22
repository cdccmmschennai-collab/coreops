import type { AccessType } from "@/features/activity-master/types";

export type { AccessType };

export interface AuthorizedEmployee {
  employee_id: string;
  employee_code: string;
  employee_name: string;
  granted_by: string | null;
  granted_at: string | null;
}

export interface ActivityAccessConfig {
  activity_id: string;
  access_type: AccessType;
  authorized_count: number;
  items: AuthorizedEmployee[];
  total: number;
  limit: number;
  offset: number;
}

export interface GrantResult {
  activity_id: string;
  access_type: AccessType;
  granted: number;
  reactivated: number;
  already_active: number;
  authorized_count: number;
}

/** Minimal shape from GET /employees for the grant picker — deliberately not the
 *  full employee record. */
export interface EmployeeSearchResult {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
}

export function employeeLabel(e: EmployeeSearchResult): string {
  return `${e.first_name} ${e.last_name}`.trim();
}

/** Employee search only fires once the query has this many non-space chars —
 *  shared by the hook (query `enabled`) and the search UI so they never
 *  disagree. */
export const EMPLOYEE_SEARCH_MIN_CHARS = 2;

export function canSearchEmployees(q: string): boolean {
  return q.trim().length >= EMPLOYEE_SEARCH_MIN_CHARS;
}

