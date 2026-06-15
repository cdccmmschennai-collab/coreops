export const submissionsKeys = {
  all: (projectId: string) => ["submissions", projectId] as const,
  detail: (projectId: string, id: string) => ["submissions", projectId, id] as const,
};
