import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deliverablesApi } from "./api";
import { deliverablesKeys } from "./keys";
import type { DeliverableCreateBody, DeliverableUpdateBody } from "./types";

export function useAllDeliverables() {
  return useQuery({
    queryKey: deliverablesKeys.globalList(),
    queryFn: () => deliverablesApi.listAll(),
  });
}

export function useDeliverables(projectId: string | undefined) {
  return useQuery({
    queryKey: deliverablesKeys.list(projectId ?? ""),
    queryFn: () => deliverablesApi.list(projectId as string),
    enabled: !!projectId,
  });
}

function useInvalidate(projectId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: deliverablesKeys.list(projectId) });
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
  const invalidate = useInvalidate(projectId);
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
