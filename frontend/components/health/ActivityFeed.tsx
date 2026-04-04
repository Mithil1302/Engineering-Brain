/**
 * ActivityFeed - Virtualized activity feed with infinite scroll
 * Task 4.8: Create ActivityFeed (virtualized with IntersectionObserver)
 */

import { useState, useRef, useEffect } from "react";
import {
  CheckCircle,
  Sparkles,
  GitBranch,
  Shield,
  TrendingUp,
  TrendingDown,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import type { ActivityEvent } from "@/lib/types";

interface ActivityFeedProps {
  activityData?: { pages: Array<{ items: ActivityEvent[] }> };
  fetchNextPage: () => void;
  hasNextPage?: boolean;
}

export function ActivityFeed({ activityData, fetchNextPage, hasNextPage }: ActivityFeedProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Flatten pages into single array
  const allEvents = activityData?.pages.flatMap((page) => page.items) ?? [];

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(sentinelRef.current);

    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage]);

  const toggleExpand = (eventId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case "doc_refresh_completed":
        return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case "doc_rewrite_generated":
        return <Sparkles className="w-4 h-4 text-blue-400" />;
      case "ci_check_run":
        return <GitBranch className="w-4 h-4 text-slate-400" />;
      case "waiver_granted":
        return <Shield className="w-4 h-4 text-amber-400" />;
      case "health_score_changed":
        return <TrendingUp className="w-4 h-4 text-emerald-400" />;
      case "policy_blocked":
        return <XCircle className="w-4 h-4 text-red-400" />;
      case "doc_gap_detected":
        return <AlertTriangle className="w-4 h-4 text-orange-400" />;
      default:
        return <CheckCircle className="w-4 h-4 text-slate-400" />;
    }
  };

  const getEventIconBg = (type: string) => {
    switch (type) {
      case "doc_refresh_completed":
        return "bg-emerald-400/10";
      case "doc_rewrite_generated":
        return "bg-blue-400/10";
      case "ci_check_run":
        return "bg-slate-400/10";
      case "waiver_granted":
        return "bg-amber-400/10";
      case "health_score_changed":
        return "bg-emerald-400/10";
      case "policy_blocked":
        return "bg-red-400/10";
      case "doc_gap_detected":
        return "bg-orange-400/10";
      default:
        return "bg-slate-400/10";
    }
  };

  if (allEvents.length === 0) {
    return (
      <div className="glass rounded-2xl p-4">
        <div className="text-sm font-semibold text-white mb-4">Activity Feed</div>
        <div className="h-[400px] flex items-center justify-center">
          <p className="text-xs text-slate-500">No recent activity</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-sm font-semibold text-white mb-4">Activity Feed</div>

      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {allEvents.map((event) => {
          const isExpanded = expandedIds.has(event.id);

          return (
            <div
              key={event.id}
              className="px-3 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 hover:bg-slate-800/70 transition-all cursor-pointer"
              onClick={() => toggleExpand(event.id)}
              style={{
                maxHeight: isExpanded ? "120px" : "56px",
                transition: "max-height 200ms ease-in-out",
              }}
            >
              <div className="flex items-start gap-3">
                <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${getEventIconBg(event.type)}`}>
                  {getEventIcon(event.type)}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300">
                    <span className="font-bold text-white">{event.entity_name}</span>{" "}
                    <span className="text-slate-400">{event.description}</span>
                  </p>

                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400">
                      {event.repo}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {formatRelativeTime(event.timestamp)}
                    </span>
                  </div>

                  {isExpanded && (
                    <div className="mt-2 p-2 rounded bg-slate-900/50 overflow-auto max-h-[60px]">
                      <pre className="text-[10px] text-slate-400 font-mono">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>

                <div className="shrink-0">
                  {isExpanded ? (
                    <ChevronUp className="w-3 h-3 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-3 h-3 text-slate-400" />
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {/* Sentinel for infinite scroll */}
        {hasNextPage && (
          <div ref={sentinelRef} className="h-4 flex items-center justify-center">
            <span className="text-xs text-slate-500">Loading more...</span>
          </div>
        )}
      </div>
    </div>
  );
}
