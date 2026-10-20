import type { CompOffListParams } from "./types";

export const compOffKeys = {
  all: ["comp-off"] as const,
  list: (params: CompOffListParams) => [...compOffKeys.all, "list", params] as const,
  detail: (id: string) => [...compOffKeys.all, "detail", id] as const,
};
