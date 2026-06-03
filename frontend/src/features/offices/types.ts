export interface Office {
  id: string;
  name: string;
  timezone: string;
  shift_start: string;
  shift_end: string;
  break_minutes: number;
  is_active: boolean;
  created_at: string;
}

export interface OfficePage {
  items: Office[];
  total: number;
  limit: number;
  offset: number;
}

export interface OfficeCreateBody {
  name: string;
  timezone: string;
  shift_start: string;
  shift_end: string;
  break_minutes: number;
  is_active?: boolean;
}

export interface OfficeUpdateBody {
  name?: string;
  timezone?: string;
  shift_start?: string;
  shift_end?: string;
  break_minutes?: number;
  is_active?: boolean;
}
