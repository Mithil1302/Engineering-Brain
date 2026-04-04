/**
 * useHealthData - React Query hook for System Health Dashboard data fetching
 * Task 4.2: Create data fetching hooks (useHealthData with React Query)
 */

import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { healthApi, reportingApi, policyApi } from "@/lib/api";
import type { HealthSnapshot, CoverageEntry, GapDay, Alert, ActivityEvent, PolicyStats } from "@/lib/types";

export function useHealthData() {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();

  // Fetch dashboard overview (latest snapshot)
  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: ["health-overview", activeRepo],
    queryFn: () => healthApi.snapshots(activeRepo!, { limit: "1" }, authHeaders()),
    enabled: !!activeRepo,
    refetchInterval: 30000,
  });

  // Fetch health snapshots (30-day)
  const { data: snapshots, isLoading: loadingSnapshots } = useQuery({
    queryKey: ["health-snapshots", activeRepo],
    queryFn: () => healthApi.snapshots(activeRepo!, { days: "30" }, authHeaders()),
    enabled: !!activeRepo,
  });

  // Fetch coverage data
  const { data: coverage, isLoading: loadingCoverage } = useQuery({
    queryKey: ["health-coverage", activeRepo],
    queryFn: () => healthApi.coverage(activeRepo!, authHeaders()),
    enabled: !!activeRepo,
  });

  // Fetch gaps for heatmap
  const { data: gapTimeline, isLoading: loadingGaps } = useQuery({
    queryKey: ["health-gaps-timeline", activeRepo],
    queryFn: () => healthApi.gapsTimeline(activeRepo!, 365, authHeaders()),
    enabled: !!activeRepo,
  });

  // Fetch active alerts
  const { data: alerts, isLoading: loadingAlerts } = useQuery({
    queryKey: ["health-alerts", activeRepo],
    queryFn: () => reportingApi.alerts(activeRepo!, "active", authHeaders()),
    enabled: !!activeRepo,
  });

  // Fetch CI pass rate stats
  const { data: ciStats, isLoading: loadingCiStats } = useQuery({
    queryKey: ["policy-stats", activeRepo],
    queryFn: () => policyApi.runsStats(activeRepo!, 7, authHeaders()),
    enabled: !!activeRepo,
  });

  // Dismiss alert mutation
  const dismissAlertMutation = useMutation({
    mutationFn: (alertId: string) => reportingApi.dismissAlert(alertId, authHeaders()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["health-alerts"] });
    },
  });

  // Fetch activity feed with infinite scroll
  const {
    data: activityData,
    fetchNextPage,
    hasNextPage,
    isLoading: loadingActivity,
  } = useInfiniteQuery({
    queryKey: ["health-activity", activeRepo],
    queryFn: ({ pageParam = null }) =>
      reportingApi.activity(activeRepo!, 20, pageParam, authHeaders()),
    getNextPageParam: (lastPage: any) => lastPage.next_cursor || undefined,
    enabled: !!activeRepo,
    initialPageParam: null,
  });

  return {
    overview: overview as { items?: HealthSnapshot[] } | undefined,
    snapshots: snapshots as { items?: HealthSnapshot[] } | undefined,
    coverage: coverage as CoverageEntry[] | undefined,
    gapTimeline: gapTimeline as GapDay[] | undefined,
    alerts: alerts as Alert[] | undefined,
    ciStats: ciStats as PolicyStats | undefined,
    activityData,
    fetchNextPage,
    hasNextPage,
    dismissAlert: dismissAlertMutation.mutate,
    isLoading:
      loadingOverview ||
      loadingSnapshots ||
      loadingCoverage ||
      loadingGaps ||
      loadingAlerts ||
      loadingCiStats ||
      loadingActivity,
  };
}
