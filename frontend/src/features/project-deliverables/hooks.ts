import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/auth-provider";

import { deliverablesApi } from "./api";
import { deliverablesKeys } from "./keys";
import type { DeliverableCreateBody, DeliverableUpdateBody } from "./types";

export function useAllDeliverables() {
  return useQuery({
    queryKey: deliverablesKeys.globalList(),
    queryFn: () => deliverablesApi.listAll(),
  });
}

/**
 * The scoped deliverables list for the login reminder banner. Enabled for
 * every authenticated user (PMs, project Heads and members); the backend
 * already limits it to projects the user may see. Shares the global-list
 * cache key with the PM dashboard card / Deliverables page.
 */
export function useMyDeliverableReminders() {
  const { status } = useAuth();
  return useQuery({
    queryKey: deliverablesKeys.globalList(),
    queryFn: () => deliverablesApi.listAll(),
    enabled: status === "authenticated",
    refetchInterval: 10 * 60_000,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}

export function useDeliverables(projectId: string | undefined) {
  return useQuery({
    queryKey: deliverablesKeys.list(projectId ?? ""),
    queryFn: () => deliverablesApi.list(projectId as string),
    enabled: !!projectId,
  });
}

export function useDeliverable(id: string | undefined) {
  return useQuery({
    queryKey: deliverablesKeys.detail(id ?? ""),
    queryFn: () => deliverablesApi.get(id as string),
    enabled: !!id,
  });
}

export function useDeliverableChanges(id: string | undefined) {
  return useQuery({
    queryKey: deliverablesKeys.changes(id ?? ""),
    queryFn: () => deliverablesApi.changes(id as string),
    enabled: !!id,
  });
}

/** Valid Assignees (project Head + members) for the create/edit form.
 *  Manager-only server-side, so only fetch while a manager has a project picked. */
export function useDeliverableAssignees(projectId: string | undefined) {
  return useQuery({
    queryKey: deliverablesKeys.assignees(projectId ?? ""),
    queryFn: () => deliverablesApi.assignees(projectId as string),
    enabled: !!projectId,
  });
}

function useInvalidate(projectId: string, id?: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: deliverablesKeys.list(projectId) });
    qc.invalidateQueries({ queryKey: deliverablesKeys.globalList() });
    if (id) {
      qc.invalidateQueries({ queryKey: deliverablesKeys.detail(id) });
      qc.invalidateQueries({ queryKey: deliverablesKeys.changes(id) });
    }
  };
}

export function useCreateDeliverable(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: DeliverableCreateBody) =>
      deliverablesApi.create(projectId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateDeliverable(projectId: string, id: string) {
  const invalidate = useInvalidate(projectId, id);
  return useMutation({
    mutationFn: (body: DeliverableUpdateBody) =>
      deliverablesApi.update(projectId, id, body),
    onSuccess: invalidate,
  });
}

export function useDeleteDeliverable(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (id: string) => deliverablesApi.delete(projectId, id),
    onSuccess: invalidate,
  });
}
