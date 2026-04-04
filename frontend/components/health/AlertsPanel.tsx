/**
 * AlertsPanel - Severity-sorted alerts with dismiss functionality
 * Task 4.7: Create AlertsPanel (severity badges, dismiss)
 */

import { useState } from "react";
import { AlertTriangle, CheckCircle, X } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";
import type { Alert } from "@/lib/types";

interface AlertsPanelProps {
  alerts?: Alert[];
  onDismiss: (alertId: string) => void;
  activeRepo: string;
}

export function AlertsPanel({ alerts, onDismiss, activeRepo }: AlertsPanelProps) {
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set());

  if (!alerts || alerts.length === 0) {
    return (
      <div className="glass rounded-2xl p-4">
        <div className="text-sm font-semibold text-white mb-4">Active Alerts</div>
        <div className="flex flex-col items-center justify-center py-8">
          <CheckCircle className="w-8 h-8 text-emerald-400 mb-2" />
          <p className="text-sm text-emerald-400">All clear — no active alerts for {activeRepo}</p>
        </div>
      </div>
    );
  }

  // Sort by severity (critical first) then timestamp descending
  const severityOrder = { CRITICAL: 0, WARNING: 1, INFO: 2 };
  const sortedAlerts = [...alerts].sort((a, b) => {
    const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
    if (severityDiff !== 0) return severityDiff;
    return new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime();
  });

  const handleDismiss = (alertId: string) => {
    setDismissingIds((prev) => new Set(prev).add(alertId));
    setTimeout(() => {
      onDismiss(alertId);
      setDismissingIds((prev) => {
        const next = new Set(prev);
        next.delete(alertId);
        return next;
      });
    }, 200);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "CRITICAL":
        return "text-red-400 bg-red-400/10 border-red-400/20";
      case "WARNING":
        return "text-amber-400 bg-amber-400/10 border-amber-400/20";
      case "INFO":
        return "text-blue-400 bg-blue-400/10 border-blue-400/20";
      default:
        return "text-slate-400 bg-slate-400/10 border-slate-400/20";
    }
  };

  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle className="w-4 h-4 text-amber-400" />
        <div className="text-sm font-semibold text-white">Active Alerts</div>
      </div>

      <div className="space-y-2 max-h-[280px] overflow-y-auto">
        {sortedAlerts.map((alert) => {
          const isDismissing = dismissingIds.has(alert.id);
          const isCritical = alert.severity === "CRITICAL";

          return (
            <div
              key={alert.id}
              className={`relative px-3 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 transition-all duration-200 ${
                isDismissing ? "opacity-0 translate-y-[-10px]" : "opacity-100"
              }`}
              style={{
                borderLeft: isCritical
                  ? "3px solid #ef4444"
                  : alert.severity === "WARNING"
                  ? "3px solid #f59e0b"
                  : "3px solid #3b82f6",
                animation: isCritical ? "pulse-border 1.5s infinite" : undefined,
              }}
            >
              <div className="flex items-start gap-2">
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase ${getSeverityColor(
                    alert.severity
                  )}`}
                >
                  {alert.severity}
                </span>

                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300">
                    {alert.message.split(alert.entity_name)[0]}
                    <span className="font-bold text-white">{alert.entity_name}</span>
                    {alert.message.split(alert.entity_name)[1]}
                  </p>

                  <div className="flex items-center gap-2 mt-1">
                    <a
                      href={alert.entity_link}
                      className="text-[10px] text-blue-400 hover:text-blue-300"
                    >
                      View details →
                    </a>
                    <span className="text-[10px] text-slate-500">
                      {formatRelativeTime(alert.triggered_at)}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => handleDismiss(alert.id)}
                  className="shrink-0 p-1 hover:bg-slate-700/50 rounded transition-colors"
                  aria-label="Dismiss alert"
                >
                  <X className="w-3 h-3 text-slate-400" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <style jsx>{`
        @keyframes pulse-border {
          0%,
          100% {
            border-left-color: #ef4444;
          }
          50% {
            border-left-color: rgba(239, 68, 68, 0.25);
          }
        }
      `}</style>
    </div>
  );
}
