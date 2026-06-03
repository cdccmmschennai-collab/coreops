import { api } from "@/lib/api-client";

import type { Office, OfficePage, OfficeCreateBody, OfficeUpdateBody } from "./types";

export const officesApi = {
  list: (limit = 50, offset = 0) =>
    api.get<OfficePage>(`/offices?limit=${limit}&offset=${offset}`),
  get: (id: string) => api.get<Office>(`/offices/${id}`),
  create: (body: OfficeCreateBody) => api.post<Office>("/offices", body),
  update: (id: string, body: OfficeUpdateBody) =>
    api.patch<Office>(`/offices/${id}`, body),
};
