export type ActivityStatus = "open" | "in_progress" | "closed";

export interface ProjectActivity {
  id: string;
  project_id: string;
  activity_type_id: string | null;
  activity_type_name: string | null;
  title: string;
  status: ActivityStatus;
  assigned_to_id: string | null;
  assigned_to_name: string | null;
  target_date: string | null;
  closed_date: string | null;
  remarks: string | null;
  sort_order: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectActivityCreateBody {
  activity_type_id?: string | null;
  title: string;
  status?: ActivityStatus;
  assigned_to_id?: string | null;
  target_date?: string | null;
  closed_date?: string | null;
  remarks?: string | null;
  sort_order?: number;
}

export interface ProjectActivityUpdateBody {
  activity_type_id?: string | null;
  title?: string;
  status?: ActivityStatus;
  assigned_to_id?: string | null;
  target_date?: string | null;
  closed_date?: string | null;
  remarks?: string | null;
  sort_order?: number;
}

export const ACTIVITY_STATUS_LABEL: Record<ActivityStatus, string> = {
  open: "Open",
  in_progress: "In Progress",
  closed: "Closed",
};
