import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { notificationsApi } from "./api";
import { notifKeys } from "./keys";
import type { NotificationListParams, UnreadCount } from "./types";

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

/** Opening the panel / page clears the badge (unseen -> seen). Unread items
 *  stay bold until clicked - only the count goes away. */
export function useMarkSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markSeen(),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: notifKeys.unreadCount() });
      qc.setQueryData<UnreadCount>(notifKeys.unreadCount(), { count: 0 });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: notifKeys.unreadCount() }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}
