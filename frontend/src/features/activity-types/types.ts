export interface ActivityType {
  id: string;
  code: string | null;
  name: string;
  category: "GENERAL" | "PROJECT" | "TAG_ESTIMATION";
  requires_project: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ActivityTypePage {
  items: ActivityType[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActivityTypeListParams {
  category?: string;
  requires_project?: boolean;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}
