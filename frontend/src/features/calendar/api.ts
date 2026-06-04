import { api } from "@/lib/api-client";

import type {
  CalendarEvent,
  CalendarEventCreateBody,
  CalendarEventListParams,
  CalendarEventPage,
} from "./types";

function toQuery(p: CalendarEventListParams): string {
  const sp = new URLSearchParams();
  if (p.from) sp.set("from", p.from);
  if (p.to) sp.set("to", p.to);
  if (p.event_type) sp.set("event_type", p.event_type);
  if (p.limit != null) sp.set("limit", String(p.limit));
  if (p.offset != null) sp.set("offset", String(p.offset));
  return sp.toString();
}

export const calendarApi = {
  list: (params: CalendarEventListParams) =>
    api.get<CalendarEventPage>(`/calendar-events?${toQuery(params)}`),
  create: (body: CalendarEventCreateBody) =>
    api.post<CalendarEvent>("/calendar-events", body),
  delete: (id: string) => api.del<void>(`/calendar-events/${id}`),
};
