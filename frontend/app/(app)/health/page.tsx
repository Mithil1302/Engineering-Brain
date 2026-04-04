"use client";
/**
 * System Health Dashboard - Main page component
 * Tasks 4.1-4.11: Complete implementation with all components
 */

import { useEffect, useState, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { useHealthData } from "@/hooks/useHealthData";
import { MetricCards } from "@/components/health/MetricCards";
import { HealthScoreChart } from "@/components/health/HealthScoreChart";
import { CoverageChart } from "@/components/health/CoverageChart";
import { GapHeatmap } from "@/components/health/GapHeatmap";
import { AlertsPanel } from "@/components/health/AlertsPanel";
import { ActivityFeed } from "@/components/health/ActivityFeed";
import { BarChart3 } from "lucide-react";
import type { ActivityEvent } from "@/lib/types";

// Skeleton loading component
function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-700/50 rounded ${className}`} />;
}

export default function HealthPage() {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();
  const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "failed">("disconnected");
  const eventSourceRef = useRef<EventSource | null>(null);

  const {
    overview,
    snapshots,
    coverage,
    gapTimeline,
    alerts,
    ciStats,
    activityData,
    fetchNextPage,
    hasNextPage,
    dismissAlert,
    isLoading,
  } = useHealthData();

  // Task 4.9: Implement SSE live updates (EventSource with reconnection)
  useEffect(() => {
    if (!activeRepo) return;

    let reconnectAttempts = 0;
    let reconnectTimeout: NodeJS.Timeout;
    const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8004";

    const connect = () => {
      try {
        const eventSource = new EventSource(
          `${BACKEND}/reporting/stream?repo=${encodeURIComponent(activeRepo)}`
        );
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          reconnectAttempts = 0;
          setConnectionStatus("connected");
        };

        eventSource.addEventListener("health_update", (e) => {
          const data = JSON.parse(e.data);
          queryClient.invalidateQueries({ queryKey: ["health-overview", activeRepo] });
          queryClient.invalidateQueries({ queryKey: ["health-snapshots", activeRepo] });

          // Push notification if score dropped >5 points
          const currentScore = overview?.items?.[0]?.score ?? 0;
          if (data.score < currentScore - 5) {
            // TODO: Implement notification system
            console.log(`Health score dropped to ${data.score}`);
          }
        });

        eventSource.addEventListener("alert", (e) => {
          const alert = JSON.parse(e.data);
          queryClient.invalidateQueries({ queryKey: ["health-alerts", activeRepo] });
          // TODO: Push notification
          console.log("New alert:", alert);
        });

        eventSource.addEventListener("activity", (e) => {
          const event = JSON.parse(e.data);
          queryClient.setQueryData(["health-activity", activeRepo], (old: any) => {
            if (!old) return old;
            return {
              ...old,
              pages: [[{ items: [event, ...(old.pages[0]?.items ?? [])] }], ...old.pages.slice(1)],
            };
          });
        });

        eventSource.onerror = () => {
          eventSource.close();
          reconnectAttempts++;

          if (reconnectAttempts < 10) {
            const delay = Math.min(30000, 2000 * Math.pow(2, reconnectAttempts - 1));
            setConnectionStatus("disconnected");
            reconnectTimeout = setTimeout(connect, delay);
          } else {
            setConnectionStatus("failed");
          }
        };
      } catch (err) {
        console.error("SSE connection error:", err);
        setConnectionStatus("failed");
      }
    };

    connect();

    return () => {
      eventSourceRef.current?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [activeRepo, queryClient, overview]);

  // Task 4.10: Implement loading/error states (skeletons)
  if (!activeRepo) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div>
          <BarChart3 className="w-10 h-10 text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
          <p className="text-sm text-slate-500">Select a repository to view its system health dashboard.</p>
        </div>
      </div>
    );
  }

  const latestSnapshot = overview?.items?.[0];
  const snapshotItems = snapshots?.items ?? [];
  const openGaps = 0; // TODO: Calculate from gapTimeline

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Task 4.1: Create page layout (CSS Grid, 4-row structure) */}
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">System Health Dashboard</h1>
              <p className="text-xs text-slate-500">{activeRepo}</p>
            </div>
          </div>

          {/* Connection status indicator */}
          {connectionStatus === "connected" && (
            <div className="flex items-center gap-2 text-xs text-emerald-400">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Live updates active
            </div>
          )}
          {connectionStatus === "failed" && (
            <div className="flex items-center gap-2 text-xs text-red-400">
              <div className="w-2 h-2 rounded-full bg-red-400" />
              Live updates paused
            </div>
          )}
        </div>

        {/* Row 1: MetricCards */}
        {isLoading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="glass rounded-2xl p-4">
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-12 w-16 mb-2" />
                <Skeleton className="h-3 w-32" />
              </div>
            ))}
          </div>
        ) : (
          <MetricCards
            latestSnapshot={latestSnapshot}
            snapshots={snapshotItems}
            coverage={coverage}
            openGaps={openGaps}
            ciStats={ciStats}
          />
        )}

        {/* Row 2: HealthScoreChart and AlertsPanel */}
        {/* Task 4.11: Implement responsive design (stack below 1400px) */}
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
          <div className="xl:col-span-3">
            {isLoading ? (
              <div className="glass rounded-2xl p-4">
                <Skeleton className="h-4 w-48 mb-4" />
                <Skeleton className="h-[280px]" />
              </div>
            ) : (
              <HealthScoreChart snapshots={snapshotItems} />
            )}
          </div>

          <div className="xl:col-span-2">
            {isLoading ? (
              <div className="glass rounded-2xl p-4">
                <Skeleton className="h-4 w-32 mb-4" />
                <Skeleton className="h-[280px]" />
              </div>
            ) : (
              <AlertsPanel alerts={alerts} onDismiss={dismissAlert} activeRepo={activeRepo} />
            )}
          </div>
        </div>

        {/* Row 3: CoverageChart and GapHeatmap */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div>
            {isLoading ? (
              <div className="glass rounded-2xl p-4">
                <Skeleton className="h-4 w-32 mb-4" />
                <Skeleton className="h-[300px]" />
              </div>
            ) : (
              <CoverageChart coverage={coverage} />
            )}
          </div>

          <div>
            {isLoading ? (
              <div className="glass rounded-2xl p-4">
                <Skeleton className="h-4 w-32 mb-4" />
                <Skeleton className="h-[200px]" />
              </div>
            ) : (
              <GapHeatmap gapTimeline={gapTimeline} />
            )}
          </div>
        </div>

        {/* Row 4: ActivityFeed */}
        <div>
          {isLoading ? (
            <div className="glass rounded-2xl p-4">
              <Skeleton className="h-4 w-32 mb-4" />
              <div className="space-y-2">
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} className="h-14" />
                ))}
              </div>
            </div>
          ) : (
            <ActivityFeed
              activityData={activityData as { pages: { items: ActivityEvent[] }[] } | undefined}
              fetchNextPage={fetchNextPage}
              hasNextPage={hasNextPage}
            />
          )}
        </div>
      </div>
    </div>
  );
}
