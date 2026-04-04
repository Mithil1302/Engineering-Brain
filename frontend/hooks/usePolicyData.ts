/**
 * usePolicyData - React Query hook for CI/CD Policy Status data fetching
 * Task 5.3: Create data fetching hooks for CI/CD Policy Status
 */

import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { policyApi, governanceApi } from "@/lib/api";
import type { PolicyRun, Waiver } from "@/lib/types";
import { useEffect, useRef, useState } from "react";

interface PolicyRunsParams {
  outcome?: string;
  ruleset?: string;
  from?: string;
  to?: string;
  search?: string;
}

interface WaiverRequest {
  rule_ids: string[];
  justification: string;
  expires_at: string;
  repo: string;
  pr_number: number;
}

export function usePolicyData(params: PolicyRunsParams = {}) {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();

  // Fetch policy runs with infinite scroll
  const {
    data: policyRunsData,
    fetchNextPage,
    hasNextPage,
    isLoading: loadingPolicyRuns,
    refetch: refetchPolicyRuns,
  } = useInfiniteQuery({
    queryKey: ["policy-runs", activeRepo, params],
    queryFn: ({ pageParam = null }) => {
      const queryParams: Record<string, string> = {
        limit: "25",
      };
      if (params.outcome) queryParams.outcome = params.outcome;
      if (params.ruleset) queryParams.ruleset = params.ruleset;
      if (params.from) queryParams.from = params.from;
      if (params.to) queryParams.to = params.to;
      if (params.search) queryParams.search = params.search;
      if (pageParam) queryParams.cursor = pageParam;

      return policyApi.runs(activeRepo!, queryParams, authHeaders());
    },
    getNextPageParam: (lastPage: any) => lastPage.next_cursor || undefined,
    enabled: !!activeRepo,
    initialPageParam: null,
  });

  // Fetch policy rulesets for filter dropdown
  const { data: rulesets, isLoading: loadingRulesets } = useQuery({
    queryKey: ["policy-rulesets", activeRepo],
    queryFn: () => policyApi.rulesets(activeRepo!, authHeaders()),
    enabled: !!activeRepo,
  });

  // Fetch selected policy run detail
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const { data: selectedRun, isLoading: loadingSelectedRun } = useQuery({
    queryKey: ["policy-run-detail", selectedRunId],
    queryFn: async () => {
      // The run detail is already in the infinite query data
      // Find it from the pages
      if (policyRunsData?.pages) {
        for (const page of policyRunsData.pages) {
          const items = (page as any).items || [];
          const run = items.find((r: PolicyRun) => r.id === selectedRunId);
          if (run) return run;
        }
      }
      return null;
    },
    enabled: !!selectedRunId && !!policyRunsData,
  });

  // Waiver request mutation
  const waiverRequestMutation = useMutation({
    mutationFn: (request: WaiverRequest) =>
      governanceApi.createWaiver(request, authHeaders()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policy-runs"] });
    },
  });

  // Waiver revoke mutation
  const waiverRevokeMutation = useMutation({
    mutationFn: (waiverId: number) =>
      governanceApi.deleteWaiver(waiverId, authHeaders()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policy-runs"] });
    },
  });

  return {
    policyRunsData,
    fetchNextPage,
    hasNextPage,
    rulesets: rulesets as string[] | undefined,
    selectedRun: selectedRun as PolicyRun | null | undefined,
    setSelectedRunId,
    requestWaiver: waiverRequestMutation.mutate,
    revokeWaiver: waiverRevokeMutation.mutate,
    refetchPolicyRuns,
    isLoading: loadingPolicyRuns || loadingRulesets || loadingSelectedRun,
  };
}

/**
 * usePolicyStream - SSE connection for real-time policy run updates
 * Implements exponential backoff reconnection as per Appendix C
 */
export function usePolicyStream() {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "failed">("disconnected");
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const disconnectTimeRef = useRef<number | null>(null);
  const [showPausedIndicator, setShowPausedIndicator] = useState(false);

  const connect = () => {
    if (!activeRepo) return;

    const headers = authHeaders();
    const url = new URL(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8004"}/policy/stream`);
    url.searchParams.set("repo", activeRepo);

    // EventSource doesn't support custom headers directly
    // We need to pass auth as query params or use a different approach
    // For now, we'll use the standard EventSource
    const eventSource = new EventSource(url.toString());

    eventSource.onopen = () => {
      setConnectionStatus("connected");
      reconnectAttemptsRef.current = 0;
      disconnectTimeRef.current = null;
      setShowPausedIndicator(false);
    };

    eventSource.addEventListener("policy_run", (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        
        // Prepend new policy run to the list via queryClient.setQueryData
        queryClient.setQueryData(
          ["policy-runs", activeRepo],
          (oldData: any) => {
            if (!oldData) return oldData;
            
            const newPages = [...oldData.pages];
            if (newPages.length > 0 && newPages[0].items) {
              newPages[0] = {
                ...newPages[0],
                items: [data, ...newPages[0].items],
              };
            }
            
            return {
              ...oldData,
              pages: newPages,
            };
          }
        );
      } catch (error) {
        console.error("Failed to parse policy_run event:", error);
      }
    });

    eventSource.onerror = () => {
      eventSource.close();
      setConnectionStatus("disconnected");
      
      if (!disconnectTimeRef.current) {
        disconnectTimeRef.current = Date.now();
      }

      // Show "Live updates paused" indicator after 5 seconds
      const timeSinceDisconnect = Date.now() - disconnectTimeRef.current;
      if (timeSinceDisconnect > 5000) {
        setShowPausedIndicator(true);
      }

      // Exponential backoff: 2s, 4s, 8s, 16s, max 30s
      if (reconnectAttemptsRef.current < 10) {
        const delay = Math.min(30000, Math.pow(2, reconnectAttemptsRef.current) * 1000);
        reconnectAttemptsRef.current++;
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else {
        setConnectionStatus("failed");
      }
    };

    eventSourceRef.current = eventSource;
  };

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [activeRepo]);

  return {
    connectionStatus,
    showPausedIndicator,
  };
}
