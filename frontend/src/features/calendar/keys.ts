import type { CalendarEventListParams } from "./types";

export const calendarKeys = {
  all: ["calendar-events"] as const,
  list: (params: CalendarEventListParams) =>
    [...calendarKeys.all, "list", params] as const,
};
