/**
 * MetricCards - Four metric cards for System Health Dashboard
 * Task 4.3: Create MetricCards (4 cards with sparklines)
 */

import { TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { getHealthColor } from "@/lib/utils";
import type { HealthSnapshot, CoverageEntry, PolicyStats } from "@/lib/types";
import Link from "next/link";

interface MetricCardProps {
  label: string;
  value: string | number;
  trend?: number;
  trendLabel?: string;
  accentColor?: string;
  sparklineData?: Array<{ value: number }>;
  actionLink?: { href: string; label: string };
}

function MetricCard({
  label,
  value,
  trend,
  trendLabel,
  accentColor = "#6366f1",
  sparklineData,
  actionLink,
}: MetricCardProps) {
  const trendPositive = trend !== undefined && trend > 0;
  const trendNegative = trend !== undefined && trend < 0;

  return (
    <div className="glass rounded-2xl p-4 relative" style={{ borderLeft: `3px solid ${accentColor}` }}>
      <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">{label}</div>
      <div className="text-5xl font-bold text-white mb-1">{value}</div>

      {trend !== undefined && (
        <div className="flex items-center gap-1 text-xs mt-2">
          {trendPositive && <TrendingUp className="w-3 h-3 text-emerald-400" />}
          {trendNegative && <TrendingDown className="w-3 h-3 text-red-400" />}
          <span className={trendPositive ? "text-emerald-400" : trendNegative ? "text-red-400" : "text-slate-400"}>
            {trend > 0 ? "+" : ""}
            {trend.toFixed(1)}% {trendLabel || "vs last week"}
          </span>
        </div>
      )}

      {sparklineData && sparklineData.length > 0 && (
        <div className="mt-2">
          <ResponsiveContainer width="100%" height={24}>
            <LineChart data={sparklineData}>
              <Line
                type="monotone"
                dataKey="value"
                stroke={accentColor}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {actionLink && (
        <Link
          href={actionLink.href}
          className="text-xs text-blue-400 hover:text-blue-300 mt-2 inline-block"
        >
          {actionLink.label} →
        </Link>
      )}
    </div>
  );
}

interface MetricCardsProps {
  latestSnapshot?: HealthSnapshot;
  snapshots?: HealthSnapshot[];
  coverage?: CoverageEntry[];
  openGaps?: number;
  ciStats?: PolicyStats;
}

export function MetricCards({ latestSnapshot, snapshots, coverage, openGaps, ciStats }: MetricCardsProps) {
  // Calculate trends
  const score = latestSnapshot?.score ?? 0;
  const scoreColor = getHealthColor(score);

  // Score trend: compare latest to 7 days ago
  const scoreTrend =
    snapshots && snapshots.length > 7
      ? ((score - snapshots[snapshots.length - 7].score) / snapshots[snapshots.length - 7].score) * 100
      : 0;

  // Coverage metrics
  const totalServices = coverage?.length ?? 0;
  const documentedServices = coverage?.filter((c) => c.coverage_percentage >= 80).length ?? 0;
  const coverageTrend = 0; // TODO: Calculate from historical data

  // Gap metrics
  const gapCount = openGaps ?? 0;
  const gapColor = gapCount > 10 ? "#ef4444" : gapCount >= 5 ? "#f59e0b" : "#22c55e";
  const gapTrend = 0; // TODO: Calculate from historical data

  // CI pass rate
  const passRate = ciStats?.pass_rate ? (ciStats.pass_rate * 100).toFixed(1) : "—";
  const ciSparkline = ciStats?.daily_pass_rates?.map((d) => ({ value: d.pass_rate * 100 })) ?? [];

  // Score sparkline (last 30 days)
  const scoreSparkline = snapshots?.slice(-30).map((s) => ({ value: s.score })) ?? [];

  return (
    <div className="grid grid-cols-4 gap-4">
      <MetricCard
        label="Knowledge Health Score"
        value={score > 0 ? score.toFixed(0) : "—"}
        trend={scoreTrend}
        accentColor={scoreColor}
        sparklineData={scoreSparkline}
      />

      <MetricCard
        label="Services Coverage"
        value={`${documentedServices} / ${totalServices}`}
        trend={coverageTrend}
        trendLabel="documented"
        accentColor="#3b82f6"
      />

      <MetricCard
        label="Documentation Gaps"
        value={gapCount}
        trend={gapTrend}
        accentColor={gapColor}
        actionLink={{ href: "/graph?filter=undocumented", label: "View gaps" }}
      />

      <MetricCard
        label="CI Pass Rate"
        value={`${passRate}%`}
        accentColor="#22c55e"
        sparklineData={ciSparkline}
      />
    </div>
  );
}
