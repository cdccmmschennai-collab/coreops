export type TaskStatus = "open" | "in_progress" | "completed" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  assigned_to_employee_id: string;
  assigned_by_employee_id: string;
  assigned_to_name: string;
  assigned_by_name: string;
  project_id: string | null;
  project_name: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssignableMember {
  employee_id: string;
  name: string;
}

export interface AssignableProject {
  project_id: string;
  name: string;
  code: string;
  members: AssignableMember[];
}

export interface TaskPage {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskListParams {
  mine?: boolean;
  q: string;
  status: TaskStatus | "";
  priority: TaskPriority | "";
  limit: number;
  offset: number;
}

export interface TaskCreateBody {
  title: string;
  description?: string | null;
  assigned_to_employee_id: string;
  project_id?: string | null;
  priority?: TaskPriority;
  due_date?: string | null;
}

export interface TaskUpdateBody {
  title?: string;
  description?: string | null;
  assigned_to_employee_id?: string;
  priority?: TaskPriority;
  due_date?: string | null;
  status?: TaskStatus;
}

export interface TaskStatusUpdateBody {
  status: TaskStatus;
}
