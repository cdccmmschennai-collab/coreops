export type DeliverableStatus = "planned" | "completed";

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
}

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
