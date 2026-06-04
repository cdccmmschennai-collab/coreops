import { api } from "@/lib/api-client";

import type {
  Notification,
  NotificationListParams,
  NotificationPage,
  UnreadCount,
} from "./types";

function toQuery(p: NotificationListParams): string {
  const sp = new URLSearchParams();
  if (p.unread_only) sp.set("unread_only", "true");
  if (p.limit != null) sp.set("limit", String(p.limit));
  if (p.offset != null) sp.set("offset", String(p.offset));
  return sp.toString();
}

export const notificationsApi = {
  list: (params: NotificationListParams) =>
    api.get<NotificationPage>(`/notifications?${toQuery(params)}`),
  unreadCount: () => api.get<UnreadCount>("/notifications/unread-count"),
  markRead: (id: string) =>
    api.post<Notification>(`/notifications/${id}/read`),
  markAllRead: () => api.post<UnreadCount>("/notifications/read-all"),
};
