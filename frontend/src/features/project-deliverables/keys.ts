export const deliverablesKeys = {
  all: ["deliverables"] as const,
  globalList: () => ["deliverables", "all"] as const,
  list: (projectId: string) => ["deliverables", "list", projectId] as const,
};
