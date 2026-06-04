import type { NotificationListParams } from "./types";

export const notifKeys = {
  all:         ["notifications"] as const,
  list:        (p: NotificationListParams) => [...notifKeys.all, "list", p] as const,
  unreadCount: () => [...notifKeys.all, "unread-count"] as const,
};
