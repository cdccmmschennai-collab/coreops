export type NotificationType =
  | "leave_submitted"
  | "leave_approved"
  | "leave_rejected"
  | "leave_cancelled"
  | "report_submitted"
  | "report_approved"
  | "report_rejected"
  | "project_assigned"
  | "calendar_event_created"
  | "employee_created"
  // Ongoing-condition notifications (upserted/resolved, not one-off events).
  | "NUMERIC_BENCHMARK"
  | "TASK_OVERDUE"
  | "SYSTEM";

export type NotificationSeverity = "INFO" | "WARNING" | "CRITICAL";

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType | string;
  title: string;
  message: string;
  severity: NotificationSeverity;
  entity_type: string | null;
  entity_id: string | null;
  target_url: string | null;
  is_read: boolean;
  // NULL = still an active/unresolved condition. Always null for one-off
  // event notifications (they're never "resolved", just read).
  resolved_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  items: Notification[];
  total: number;
  limit: number;
  offset: number;
}

export interface UnreadCount {
  count: number;
}

export interface NotificationListParams {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
}
