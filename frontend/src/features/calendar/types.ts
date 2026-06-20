export type CalendarEventType =
  | "holiday"
  | "cdc_holiday"
  | "natural_hazard"
  | "working_day"
  | "event";

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
  cdc_holiday: "CDC Holiday",
  natural_hazard: "Natural Hazard",
  working_day: "Working Day",
  event: "Event",
};

/** Badge styling (background + text) per category, for list chips. */
export const EVENT_TYPE_BADGE: Record<CalendarEventType, string> = {
  holiday: "bg-violet-50 text-violet-700",
  cdc_holiday: "bg-blue-50 text-blue-700",
  natural_hazard: "bg-red-50 text-red-700",
  working_day: "bg-emerald-50 text-emerald-700",
  event: "bg-slate-100 text-slate-700",
};

/** Categories that CLOSE the office (render as an off/holiday day). */
export const OFF_EVENT_TYPES: CalendarEventType[] = [
  "holiday",
  "cdc_holiday",
  "natural_hazard",
];

/** Categories selectable when adding an entry, in display order. */
export const SELECTABLE_EVENT_TYPES: CalendarEventType[] = [
  "holiday",
  "cdc_holiday",
  "natural_hazard",
  "working_day",
];

export function isOffEvent(type: CalendarEventType): boolean {
  return OFF_EVENT_TYPES.includes(type);
}
