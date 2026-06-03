export const officesKeys = {
  all: ["offices"] as const,
  list: () => [...officesKeys.all, "list"] as const,
  detail: (id: string) => [...officesKeys.all, "detail", id] as const,
};
