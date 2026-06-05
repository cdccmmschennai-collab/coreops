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
  | "employee_created";

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType | string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  target_url: string | null;
  is_read: boolean;
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
