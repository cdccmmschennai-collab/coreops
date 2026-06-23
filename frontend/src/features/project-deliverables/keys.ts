export const deliverablesKeys = {
  all: ["deliverables"] as const,
  globalList: () => ["deliverables", "all"] as const,
  list: (projectId: string) => ["deliverables", "list", projectId] as const,
  detail: (id: string) => ["deliverables", "detail", id] as const,
  changes: (id: string) => ["deliverables", "changes", id] as const,
};
