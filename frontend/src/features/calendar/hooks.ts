import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { calendarApi } from "./api";
import { calendarKeys } from "./keys";
import type { CalendarEventCreateBody, CalendarEventListParams } from "./types";

export function useCalendarEvents(params: CalendarEventListParams) {
  return useQuery({
    queryKey: calendarKeys.list(params),
    queryFn: () => calendarApi.list(params),
    placeholderData: (prev) => prev,
  });
}

export function useCreateCalendarEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CalendarEventCreateBody) => calendarApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}

export function useDeleteCalendarEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => calendarApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: calendarKeys.all }),
  });
}
