import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { onboardingApi } from "@/lib/api";
import { OnboardingPath, OnboardingRole } from "@/lib/types";

export function useOnboardingData(
  repo: string,
  role: OnboardingRole | null,
  authHeaders: () => Record<string, string>
) {
  const queryClient = useQueryClient();

  // Fetch onboarding path for role
  const pathQuery = useQuery<OnboardingPath>({
    queryKey: ["onboarding-path", repo, role],
    queryFn: async () => {
      const data = await onboardingApi.getPath(repo, role!, authHeaders());
      return data as OnboardingPath;
    },
    enabled: !!repo && !!role,
    staleTime: 30000,
  });

  // Update stage progress mutation with optimistic update
  const updateProgressMutation = useMutation({
    mutationFn: (data: { stage_id: string; user_id: string; repo: string; completed_at: string }) =>
      onboardingApi.updateProgress(data, authHeaders()),
    onMutate: async (data) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["onboarding-path", repo, role] });

      // Snapshot previous value
      const previousPath = queryClient.getQueryData<OnboardingPath>(["onboarding-path", repo, role]);

      // Optimistically update
      if (previousPath) {
        queryClient.setQueryData<OnboardingPath>(["onboarding-path", repo, role], {
          ...previousPath,
          stages: previousPath.stages?.map((stage) =>
            stage.stage_id === data.stage_id
              ? { ...stage, completed: true }
              : stage
          ),
        });
      }

      return { previousPath };
    },
    onError: (_err, _data, context) => {
      // Rollback on error
      if (context?.previousPath) {
        queryClient.setQueryData(["onboarding-path", repo, role], context.previousPath);
      }
    },
    onSettled: () => {
      // Refetch after mutation
      queryClient.invalidateQueries({ queryKey: ["onboarding-path", repo, role] });
    },
  });

  // Mark resource read mutation
  const markResourceReadMutation = useMutation({
    mutationFn: (data: { resource_id: string; user_id: string; repo: string }) =>
      onboardingApi.updateResourceProgress(data, authHeaders()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["onboarding-path", repo, role] });
    },
  });

  return {
    path: pathQuery.data,
    isLoading: pathQuery.isLoading,
    isError: pathQuery.isError,
    error: pathQuery.error,
    updateProgress: updateProgressMutation.mutate,
    markResourceRead: markResourceReadMutation.mutate,
    isUpdating: updateProgressMutation.isPending,
  };
}
