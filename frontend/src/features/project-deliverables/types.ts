export type DeliverableStatus = "pending" | "in_progress" | "completed";

export interface Deliverable {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
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
  target_date?: string | null;
  owner_employee_id?: string | null;
  status?: DeliverableStatus;
  completion_date?: string | null;
}

export interface DeliverableUpdateBody {
  name?: string;
  description?: string | null;
  target_date?: string | null;
  owner_employee_id?: string | null;
  status?: DeliverableStatus;
  completion_date?: string | null;
}

export const DELIVERABLE_STATUS_LABEL: Record<DeliverableStatus, string> = {
  pending: "Pending",
  in_progress: "In Progress",
  completed: "Completed",
};
