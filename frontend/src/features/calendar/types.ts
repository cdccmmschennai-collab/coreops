export type CalendarEventType = "holiday" | "event";

export interface CalendarEvent {
  id: string;
  event_date: string;
  title: string;
  event_type: CalendarEventType;
  description: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarEventPage {
  items: CalendarEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface CalendarEventCreateBody {
  event_date: string;
  title: string;
  event_type?: CalendarEventType;
  description?: string | null;
}

export interface CalendarEventListParams {
  from?: string;
  to?: string;
  event_type?: CalendarEventType;
  limit?: number;
  offset?: number;
}

export const EVENT_TYPE_LABEL: Record<CalendarEventType, string> = {
  holiday: "Holiday",
  event: "Event",
};
