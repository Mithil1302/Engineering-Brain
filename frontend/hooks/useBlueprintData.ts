import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { blueprintsApi } from "@/lib/api";
import type { Blueprint } from "@/lib/types";

export function useBlueprintList(filters: {
  pattern: string | null;
  from: string | null;
  to: string | null;
  aligned: boolean | null;
}) {
  const { activeRepo, authHeaders } = useSession();

  const params: Record<string, string> = {};
  if (filters.pattern) params.pattern = filters.pattern;
  if (filters.from) params.from = filters.from;
  if (filters.to) params.to = filters.to;
  if (filters.aligned !== null) params.aligned = filters.aligned.toString();

  return useQuery({
    queryKey: ["blueprints", activeRepo, params],
    queryFn: () => blueprintsApi.list(activeRepo!, params, authHeaders()),
    enabled: !!activeRepo,
    staleTime: 30000,
  });
}

export function useBlueprintDetail(blueprintId: string | null) {
  const { authHeaders } = useSession();

  return useQuery({
    queryKey: ["blueprint", blueprintId],
    queryFn: () => blueprintsApi.get(blueprintId!, authHeaders()),
    enabled: !!blueprintId,
    staleTime: 30000,
  });
}

export function useBlueprintArtifact(blueprintId: string | null, filePath: string | null) {
  const { authHeaders } = useSession();

  return useQuery({
    queryKey: ["blueprint-artifact", blueprintId, filePath],
    queryFn: () => blueprintsApi.artifact(blueprintId!, filePath!, authHeaders()),
    enabled: !!blueprintId && !!filePath,
    staleTime: 60000,
  });
}

export function useReanalyzeAlignment() {
  const queryClient = useQueryClient();
  const { authHeaders } = useSession();

  return useMutation({
    mutationFn: (blueprintId: string) =>
      blueprintsApi.analyze(blueprintId, authHeaders()),
    onSuccess: (_, blueprintId) => {
      queryClient.invalidateQueries({ queryKey: ["blueprint", blueprintId] });
      queryClient.invalidateQueries({ queryKey: ["blueprints"] });
    },
  });
}
