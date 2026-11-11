import type { components } from "@/types/openapi";

export type DeliverableStatus = "planned" | "completed";

/**
 * Submission-deadline state, DERIVED BY THE BACKEND (deadline.py, IST "today")
 * and never stored - ADR-003 Amendment 2. The frontend only displays it; it
 * must never recompute it from the browser's local date.
 *
 *   overdue      past the deadline, still planned
 *   due_today    0 days left
 *   urgent       1 day left
 *   due_soon     2-5 days left (the five-day reminder window)
 *   on_track     more than 5 days left
 *   no_deadline  planned, no target date
 *   completed    status is completed
 */
export type DeadlineState =
  | "overdue"
  | "due_today"
  | "urgent"
  | "due_soon"
  | "on_track"
  | "no_deadline"
  | "completed";

export interface Deliverable {
  id: string;
  project_id: string;
  /** Populated by the backend on the global list endpoint only (null elsewhere). */
  project_name: string | null;
  /** Populated by the backend on the global list endpoint only (null elsewhere). */
  project_code: string | null;
  name: string;
  description: string | null;
  planned_start_date: string | null;
  target_date: string | null;
  owner_employee_id: string | null;
  owner_name: string | null;
  status: DeliverableStatus;
  completion_date: string | null;
  created_at: string;
  updated_at: string;
  /** Signed days until the deadline (0 = today, negative = overdue); null when
   *  there is no deadline or it is completed. Backend-computed. */
  days_remaining: number | null;
  deadline_state: DeadlineState;
  /** Whether the caller may create/edit/delete on this row's project
   *  (PM, or the project's Head). The backend still enforces it. */
  can_manage: boolean;
}

// ── contract guard ──────────────────────────────────────────────────────────
// These types are hand-written for readability. The assertions below fail
// `tsc` if they drift from the generated backend contract (src/types/openapi.ts,
// regenerated from DeliverableOut) - type-level only, nothing ships at runtime.
type ApiDeliverableOut = components["schemas"]["DeliverableOut"];
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
type Assert<T extends true> = T;
export type _DeliverableContractCheck = [
  Assert<Exact<DeadlineState, ApiDeliverableOut["deadline_state"]>>,
  Assert<Exact<DeliverableStatus, ApiDeliverableOut["status"]>>,
  Assert<Exact<Deliverable["days_remaining"], ApiDeliverableOut["days_remaining"]>>,
  Assert<Exact<Deliverable["can_manage"], ApiDeliverableOut["can_manage"]>>,
  // Every field the backend sends exists on the frontend type, and vice versa.
  Assert<Exact<keyof Deliverable, keyof ApiDeliverableOut>>,
];

export interface DeliverableCreateBody {
  name: string;
  description?: string | null;
  planned_start_date?: string | null;
  target_date?: string | null;
  owner_employee_id?: string | null;
  status?: DeliverableStatus;
  completion_date?: string | null;
}

export interface DeliverableUpdateBody {
  name?: string;
  description?: string | null;
  planned_start_date?: string | null;
  target_date?: string | null;
  owner_employee_id?: string | null;
  status?: DeliverableStatus;
  completion_date?: string | null;
  /** Mandatory when changing planned start date, due date, or reverting status. */
  reason?: string;
}

/** One row of a deliverable's change history (append-only audit trail). */
export type DeliverableChangeFieldKey = "planned_start_date" | "due_date" | "status";

export interface DeliverableChange {
  id: string;
  deliverable_id: string;
  field: DeliverableChangeFieldKey | string;
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  changed_by_name: string;
  reason: string;
  changed_at: string;
}

export const DELIVERABLE_STATUS_LABEL: Record<DeliverableStatus, string> = {
  planned: "Planned",
  completed: "Completed",
};

export const DELIVERABLE_CHANGE_FIELD_LABEL: Record<string, string> = {
  planned_start_date: "Start Date",
  due_date: "Planned Submission",
  status: "Status",
};
