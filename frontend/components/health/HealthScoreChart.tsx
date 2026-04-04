/**
 * HealthScoreChart - Recharts AreaChart for 30-day health score trend
 * Task 4.4: Create HealthScoreChart (Recharts AreaChart)
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from "recharts";
import { getHealthColor } from "@/lib/utils";
import type { HealthSnapshot } from "@/lib/types";

interface HealthScoreChartProps {
  snapshots?: HealthSnapshot[];
}

export function HealthScoreChart({ snapshots }: HealthScoreChartProps) {
  if (!snapshots || snapshots.length === 0) {
    return (
      <div className="glass rounded-2xl p-4">
        <div className="text-sm font-semibold text-white mb-4">Health Score Trend (30 days)</div>
        <div className="h-[280px] flex items-center justify-center">
          <p className="text-xs text-slate-500">No health history available</p>
        </div>
      </div>
    );
  }

  // Prepare chart data
  const chartData = snapshots.map((s) => ({
    date: new Date(s.produced_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    score: parseFloat(s.score.toFixed(1)),
    timestamp: new Date(s.produced_at).getTime(),
  }));

  // Get latest score for color
  const latestScore = chartData[chartData.length - 1]?.score ?? 50;
  const strokeColor = getHealthColor(latestScore);

  // Detect 7-day windows with score drop > 15 points
  const dropWindows: Array<{ x1: string; x2: string }> = [];
  for (let i = 0; i < chartData.length - 7; i++) {
    const startScore = chartData[i].score;
    const endScore = chartData[i + 7].score;
    if (startScore - endScore > 15) {
      dropWindows.push({
        x1: chartData[i].date,
        x2: chartData[i + 7].date,
      });
    }
  }

  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-sm font-semibold text-white mb-4">Health Score Trend (30 days)</div>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="healthGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity={0.3} />
              <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={true} vertical={false} />

          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
          />

          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
          />

          <Tooltip
            contentStyle={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#94a3b8" }}
            itemStyle={{ color: "#a5b4fc" }}
          />

          {/* Reference lines */}
          <ReferenceLine
            y={80}
            stroke="#f59e0b"
            strokeDasharray="4 2"
            label={{ value: "Target", position: "right", fill: "#f59e0b", fontSize: 10 }}
          />
          <ReferenceLine
            y={50}
            stroke="#ef4444"
            strokeDasharray="4 2"
            label={{ value: "Warning", position: "right", fill: "#ef4444", fontSize: 10 }}
          />

          {/* Reference areas for score drops */}
          {dropWindows.map((window, i) => (
            <ReferenceArea
              key={i}
              x1={window.x1}
              x2={window.x2}
              fill="#ef4444"
              fillOpacity={0.15}
            />
          ))}

          <Area
            type="monotone"
            dataKey="score"
            stroke={strokeColor}
            strokeWidth={2}
            fill="url(#healthGradient)"
            dot={false}
            activeDot={{ r: 4 }}
            animationDuration={1000}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
