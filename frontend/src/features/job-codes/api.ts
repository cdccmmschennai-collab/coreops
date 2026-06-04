import { api } from "@/lib/api-client";
import type { JobCodePage, JobCodeListParams } from "./types";

function toQuery(p: JobCodeListParams): string {
  const sp = new URLSearchParams();
  if (p.active_only !== undefined) sp.set("active_only", String(p.active_only));
  sp.set("limit", String(p.limit ?? 200));
  sp.set("offset", String(p.offset ?? 0));
  return sp.toString();
}

export const jobCodesApi = {
  list: (params: JobCodeListParams = {}) =>
    api.get<JobCodePage>(`/job-codes?${toQuery(params)}`),
};
