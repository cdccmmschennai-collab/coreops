import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export interface LedProjectMember { employee_id: string; name: string }
export interface LedProject { project_id: string; name: string; code: string; members: LedProjectMember[] }

export function useLedProjects({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["projects", "led"],
    queryFn: () => api.get<LedProject[]>("/projects/led"),
    enabled,
  });
}
