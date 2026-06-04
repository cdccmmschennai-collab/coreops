import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { notificationsApi } from "./api";
import { notifKeys } from "./keys";
import type { NotificationListParams } from "./types";

export function useNotifications(params: NotificationListParams = {}) {
  return useQuery({
    queryKey: notifKeys.list(params),
    queryFn: () => notificationsApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: notifKeys.unreadCount(),
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 60_000,          // poll every 60 s
    refetchOnWindowFocus: true,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}
