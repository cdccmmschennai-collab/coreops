export interface JobCode {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface JobCodePage {
  items: JobCode[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobCodeListParams {
  active_only?: boolean;
  limit?: number;
  offset?: number;
}
